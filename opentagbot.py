#!/usr/bin/env python3
import configparser
import signal
import time
import sqlite3
import telepot
import sys


class OpenTagBot(telepot.Bot):
    def __init__(self, database, *args, **kwargs):
        super(OpenTagBot, self).__init__(*args, **kwargs)
        self._answerer = telepot.helper.Answerer(self)

        if not isinstance(database, TagBotDatabase):
            raise TypeError('Need my database as argument!')
        self.db = database
        print(self.getMe()['username'] + " started")

        self.mycommands = {
            '/register': self.command_register,
            '/delete': self.command_delete,
            '/start': self.command_start,
            '/opensource': self.command_opensource,
            '/help': self.command_help
        }

    @staticmethod
    def sigterm_handler(signal, frame):
        print("got SIGTERM")
        raise SigTermException

    def exit_gracefully(self):
        db.close_database()

    def on_chat_message(self, msg):

        message = msg['text']
        words = message.split()
        first_word = words[0].replace("@{botname}".format(botname=self.getMe()['username']), "")
        if first_word in self.mycommands:
            self.call_associated_method(first_word, msg)
        if "@" not in message:
            return
        for word in words:
            if word[0] != "@":
                continue
            chat_id_mentioned = self.db.get_chat_id_for_handle(word[1:])
            user_id_mentioned = self.db.get_user_id_for_chat_id(chat_id_mentioned)
            if chat_id_mentioned:
                self.notify_user(chat_id_mentioned, msg)

    def call_associated_method(self, commandstring, msg):
        self.mycommands[commandstring](msg)

    def notify_user(self, chat_id_mentioned, msg):
        incoming_chat_id = msg['chat']['id']
        user_id_mentioned = self.db.get_user_id_for_chat_id(chat_id_mentioned)
        chatmember = self.getChatMember(incoming_chat_id, user_id_mentioned)
        if chatmember['status'] not in {'creator', 'administrator', 'member'}:
            return
        if msg['chat']['type'] == 'private':
            return
        self.forwardMessage(
            chat_id=chat_id_mentioned,
            from_chat_id=msg['chat']['id'],
            message_id=msg['message_id']
        )

    def command_register(self, msg):
        sender = msg['chat']['id']
        username = msg['from'].get('username', None)
        uid = msg['from']['id']
        type = msg['chat']['type']

        if type != 'private':
            message = (
                "Almost! Please send me a private message to do this: @{botname}"
            ).format(botname=self.getMe()['username'])
        elif self.db.register_user(uid, sender, username):
            message = (
                'You are now registered as @{username}. '
                'I will send you a message as soon as you are tagged somewhere - '
                'use /delete anytime to cancel this service.'
                ' Remember to come back and /register again if your @ nickname has changed!'
            ).format(username=username)
        else:
            message = 'Could not register you - have you set your @ nickname already?'

        self.sendMessage(sender, message)

    def command_delete(self, msg):
        sender = msg['chat']['id']
        type = msg['chat']['type']

        if type != 'private':
            message = (
                'This seems a bit indiscreet for me. Can you please send me a private message at @{botname}'
                ', so we can talk about this privately?'
            ).format(botname=self.getMe()['username'])
        elif self.db.delete_user(sender):
            message = 'I deleted your nickname, you will no longer receive notifications. Bye!'
        else:
            message = (
                'You are not currently registered, have nothing to delete. You can /register yourself to start '
                'using this service!'
            )

        self.sendMessage(sender, message)

    def command_start(self, msg):
        sender = msg['chat']['id']
        username = msg['from'].get('username', None)
        type = msg['chat']['type']

        if username:
            include_name = '@' + username + '.'
            name_hint = ''
        else:
            include_name = 'your username.'
            name_hint = 'Head over to your Telegram settings first to set your username.'

        if type != 'private':
            message = ("Heya! Nice of you to add me to this group. "
                       "If you send me a private message (@{botname}), "
                       "I can start sending you notifications whenever you get tagged with your @ nickname "
                       "in this group. I won't spy on you guys, promised! Type /opensource for more information"
                       ).format(botname=self.getMe()['username'])
        else:
            message = ("Hi there! I can to send you a message whenever you are mentioned with "
                       "{include_name}"
                       " If you like that, type /register to get started."
                       " {name_hint}"
                       " It's important to add me to your groups, so I can actually see the messages you get tagged in."
                       " I won't spy on you, promised! Type /opensource for more information"
                       ).format(include_name=include_name, name_hint=name_hint)

        self.sendMessage(sender, message)

    def command_opensource(self, msg):
        sender = msg['chat']['id']
        message = (
            "You can view my source code here: https://github.com/AmbassadorTux/opentagbot . "
            "The bot aims to absolutely only process @ mentions of registred users and a few commands. "
            "Privacy matters! \n\n"
            "I guess there's no way to guarantee that this bot is actually running the source at hand, although "
            "I aim to do that. But don't take my word for it - just clone/fork that repository and setup your "
            "own bot, if you don't trust me (which is reasonable). "
            "It works almost out-of-the-box, just follow the instructions "
            "on the command line on first run :-)"
        )
        self.sendMessage(sender, message)

    def command_help(self, msg):
        sender = msg['chat']['id']
        message = (
            "Look buddy, it's not as hard as you might think.\n"
            "1. Send this to me: /register\n"
            "2. Invite me to all your groups\n"
            "3. ??? \n"
            "4. Profit!"
        )
        self.sendMessage(sender, message)


class TagBotDatabase:
    def __init__(self):
        self.db = sqlite3.connect('opentagbot_database.sqlite3', check_same_thread=False)
        print('Initializing database...')
        self.init_database()

    def init_database(self):
        """
        Creates the needed tables
        :return:
        """
        c = self.db.cursor()
        c.execute(
            'CREATE TABLE IF NOT EXISTS "users" '
            '("user_id" INTEGER PRIMARY KEY, "chat_id" INTEGER NOT NULL, "handle" INTEGER NOT NULL);'
        )
        c.close()
        self.db.commit()

    def register_user(self, user_id, chat_id, handle):
        """
        Registers or updates a user

        :param user_id: The user's ID
        :param chat_id: The corresponding chat ID
        :param handle: The user's Handle without @
        :return:
        """

        if not handle or not chat_id or not user_id:
            return False

        c = self.db.cursor()
        d = self.db.cursor()
        c.execute('SELECT chat_id FROM users WHERE chat_id = ?', (chat_id,))
        result = c.fetchone()
        if not result:
            d.execute('INSERT INTO users (user_id, chat_id, handle) VALUES (?, ?, ?)', (user_id, chat_id, handle))
        else:
            d.execute('UPDATE users SET handle = ?, chat_id = ? WHERE user_id = ?', (handle, chat_id, user_id))
        rowcount = d.rowcount
        d.close()
        self.db.commit()
        return rowcount

    def delete_user(self, chat_id):
        """
        Deletes a user from the database
        :param chat_id: The user ID to be deleted
        :return:
        """
        if not chat_id:
            return False

        c = self.db.cursor()
        c.execute('DELETE FROM users WHERE chat_id = ?', (chat_id,))
        rowcount = c.rowcount
        c.close()
        self.db.commit()
        return rowcount

    def get_chat_id_for_handle(self, handle):
        """
        Tries to find the user ID for a given handle
        :param handle: user handle, without @
        :return: the corresponding chat ID or False, if not found
        """
        if not handle:
            return False

        c = self.db.cursor()
        c.execute('SELECT chat_id FROM users WHERE handle = ? LIMIT 1', (handle,))
        row = c.fetchone()
        c.close()
        if row:
            return row[0]
        else:
            return False


    def get_user_id_for_chat_id(self, chat_id):
        """
        Tries to find the chat ID for a given user ID
        :param chat_id: chat ID
        :return: the corresponding user ID or False, if not found
        """
        if not chat_id:
            return False

        c = self.db.cursor()
        c.execute('SELECT user_id FROM users WHERE chat_id = ? LIMIT 1', (chat_id,))
        row = c.fetchone()
        c.close()
        if row:
            return row[0]
        else:
            return False

    def close_database(self):
        self.db.commit()
        self.db.close()


class Configuration:
    BOTNAME = 'opentagbot'
    PLACEHOLDER = 'YOUR-API-KEY-HERE'

    def __init__(self, filename):
        self.filename = filename
        self.confparse = configparser.ConfigParser()
        self.confparse.read(filename)

        # check if we have a config already
        if not self.confparse.has_section(self.BOTNAME)\
                or self.confparse.get(self.BOTNAME, 'api_key') == self.PLACEHOLDER:
            print('No configuration has been created, yet.')
            print('Please edit ' + filename + ' and restart the bot!')
            self.set_defaults()
            self.write_config()
            sys.exit(1)

        self.api_key = ''
        self.read_config()

    def set_defaults(self):
        self.confparse[self.BOTNAME] = {
            'api_key': self.PLACEHOLDER,
        }

    def write_config(self):
        with open(self.filename, 'w') as config_file:
            self.confparse.write(config_file)

    def read_config(self):
        self.confparse.read(self.filename)
        self.api_key = self.confparse.get(self.BOTNAME, 'api_key')


class SigTermException(Exception):
    pass


def sigterm_handler(signal, frame):
    print("Goodbye!")
    global sigterm_received
    sigterm_received = True


""" Start the Bot """
print('Starting...')
db = TagBotDatabase()
conf = Configuration('opentagbot_config.ini')
bot = OpenTagBot(db, conf.api_key)

signal.signal(signal.SIGTERM, bot.sigterm_handler)

try:
    bot.message_loop()

    # Keep the program running.
    while 1:
        time.sleep(10)

except (KeyboardInterrupt, SystemExit, SigTermException):
    bot.exit_gracefully()
    conf.write_config()
    print('Goodbye!')
    raise

print('Finished')
