#!/usr/bin/env python3
import configparser
import signal
import sched, time
import sqlite3

import sys
import twx.botapi
#import telepot

class OpenTagBot:
    class Configuration:
        def __init__(self, filename):
            self.filename = filename
            self.confparse = configparser.ConfigParser()
            self.confparse.read(filename)

            # check if we have a config already
            if not self.confparse.has_section('opentagbot'):
                print('No configuration has been created, yet.')
                print('Please edit ' + filename + ' and restart the bot!')
                self.set_defaults()
                self.write_config()
                sys.exit(1)

            self.api_key = ''
            self.msg_offset = 0
            self.read_config()
            self.scheduler = sched.scheduler()
            self.scheduler.enter(60, 1, self.update_config, (self.scheduler,))

        def set_defaults(self):
            self.confparse['opentagbot'] = {
                'api_key': 'YOUR-API-KEY-HERE',
            }

        def write_config(self):
            with open(self.filename, 'w') as config_file:
                self.confparse.write(config_file)

        def read_config(self):
            self.confparse.read(self.filename)
            self.api_key = self.confparse.get('opentagbot', 'api_key')
            self.msg_offset = int(self.confparse.get('opentagbot', 'msg_offset', fallback=0))

        def update_config(self, *args):
            self.write_config()
            self.scheduler.enter(60, 1, self.update_config, (self.scheduler,))

    def __init__(self, database):
        self.conf = self.Configuration('opentagbot_config.ini')
        if not isinstance(database, TagBotDatabase):
            raise TypeError('Need my database as argument!')
        self.bot = twx.botapi.TelegramBot(self.conf.api_key)
        self.bot.update_bot_info().wait()
        self.msg_offset = 0
        print(self.bot.username + " started")

    def pull_updates(self):
        updates = self.bot.get_updates(offset=self.msg_offset).wait()
        print(self.msg_offset)
        for update in updates:
            self.process_update(update)
            self.msg_offset = update.update_id + 1

    def process_update(self, update):
        print(update)

    def sigterm_handler(signal, frame):
        print("got SIGTERM")
        raise SigTermException

    def exit_gracefully(self):
        db.close_database()
        self.conf.write_config()


class TagBotDatabase:
    def __init__(self):
        self.db = sqlite3.connect('opentagbot_database.sqlite3')
        c = self.db.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if c.rowcount == 0:
            print('Initializing database...')
            c.close()
            self.init_database()

    def init_database(self):
        """
        Creates the needed tables
        :return:
        """
        c = self.db.cursor()
        c.execute(
            'CREATE TABLE IF NOT EXISTS "main"."users" ( "userid" INTEGER PRIMARY KEY, "handle" INTEGER NOT NULL);'
        )
        c.close()

    def register_user(self, userid, handle):
        """
        Registers or updates a user

        :param userid: The user's ID
        :param handle: The user's Handle without @
        :return:
        """
        c = self.db.cursor()
        d = self.db.cursor()
        c.execute('SELECT userid FROM users WHERE userid = ?', userid)
        if c.rowcount == 0:
            d.execute('INSERT INTO users (userid, handle) VALUES (?, ?)', (userid, handle))
        else:
            d.execute('UPDATE users SET handle = ? WHERE userid = ?', (handle, userid))
        d.close()

    def delete_user(self, userid):
        """
        Deletes a user from the database
        :param userid: The user ID to be deleted
        :return:
        """
        c = self.db.cursor()
        c.execute('DELETE FROM users WHERE userid = ?', userid)

    def lookup_handle(self, handle):
        """
        Tries to find the user ID for a given handle
        :param handle: user handle, without @
        :return: the corresponding user ID or False, if not found
        """
        c = self.db.cursor()
        c.execute('SELECT userid FROM users WHERE handle = ? LIMIT 1', handle)
        if c.rowcount == 0:
            return False
        row = c.fetchone()
        c.close()
        return row['userid']

    def close_database(self):
        self.db.close()


class SigTermException(Exception):
    pass


def sigterm_handler(signal, frame):
    print("Goodbye!")
    global sigterm_received
    sigterm_received = True


""" Start the Bot """
print('Starting...')
db = TagBotDatabase()
bot = OpenTagBot(db)

signal.signal(signal.SIGTERM, bot.sigterm_handler)

try:
    while True:
        bot.pull_updates()
        time.sleep(3)
except (KeyboardInterrupt, SystemExit, SigTermException):
    bot.exit_gracefully()
    print('Goodbye!')
    raise

print('Finished')
