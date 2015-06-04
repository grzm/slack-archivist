"""Archivist CLI

Usage:
  cli.py list
  cli.py invite <human_name> <bot_name>
  cli.py export <output_dir>
  cli.py (-h | --help)
  cli.py --version

Options:
  -h --help     Show this screen.
  --version     Show version.

"""

import os
import json
import shutil
from glob import glob
from collections import defaultdict
from datetime  import datetime

from docopt import docopt
import pystache
import yaml
from slackclient import SlackClient

if __name__ == "__main__":
    arguments = docopt(__doc__, version='Slack Archivist v0.1')
    config = yaml.load(file('rtmbot.conf', 'r'))
    sc = SlackClient(config['SLACK_TOKEN'])
    human = SlackClient(config['HUMAN_SLACK_TOKEN'])

    if arguments['list']:
        print ', '.join([c['name'] for c in json.loads(sc.api_call('channels.list'))['channels']])

    elif arguments['invite']:
        channels = json.loads(sc.api_call('channels.list'))['channels']
        members = json.loads(sc.api_call('users.list'))['members']

        bot_name = arguments['<bot_name>']
        human_name = arguments['<human_name>']
        bot_id = None
        human_id = None

        for member in members:
            if member['name'] == bot_name:
                bot_id = member['id']
            elif member['name'] == human_name:
                human_id = member['id']
            if bot_id and human_id:
                break

        if bot_id is None:
            raise Exception('Bot %s is not found.' % bot_name)
        if human_id is None:
            raise Exception('Human %s is not found.' % human_name)

        for channel in channels:
            print '>>>', channel['name']

            chan_id = channel['id']
            is_human_in_chan = False
            is_bot_in_chan = False

            for member in json.loads(sc.api_call('channels.info', channel=chan_id))['channel']['members']:
                if member == human_id:
                    is_human_in_chan = True
                elif member == bot_id:
                    is_bot_in_chan = True
                    break

            if is_bot_in_chan:
                print "already in chan"
                continue

            if not is_human_in_chan:
                print "join"
                human.api_call('channels.join', name=channel['name'])

            print human.api_call('channels.invite', channel=chan_id, user=bot_id)

            if not is_human_in_chan:
                print "leave"
                human.api_call('channels.leave', channel=chan_id)

    elif arguments['export']:
        channels = json.loads(sc.api_call('channels.list'))['channels']
        members = json.loads(sc.api_call('users.list'))['members']

        channels = {x['id']: x for x in channels}
        members = {x['id']: x for x in members}

        data = defaultdict(lambda: defaultdict(list))

        for p in glob('logs/*.txt'):
            date, _ = os.path.splitext(os.path.basename(p))
            with open(p, 'rb') as f:
                for msg in f:
                    msg = json.loads(msg)
                    user_id = msg['user']
                    msg['user'] = members[user_id]['name']
                    msg['avatar'] = members[user_id]['profile']['image_48']
                    msg['timestamp'] = datetime.fromtimestamp(float(msg['ts'])).strftime('%H:%M:%S')
                    data[channels[msg['channel']]['name']][date].append(msg)

        out_dir = arguments['<output_dir>']

        shutil.copy2('template/global.css', out_dir)

        renderer = pystache.Renderer(search_dirs='template')
        for channel_name, dates in data.iteritems():
            p = os.path.join(out_dir, channel_name)
            try:
                os.makedirs(p)
            except OSError:
                pass
            for date, msgs in dates.iteritems():
                with open(os.path.join(p, date) + '.html', 'wb') as f:
                    f.write(renderer.render_path('template/index.mustache', {'active_channel': channel_name,
                                                                             'channels': channels.values(),
                                                                             'messages': msgs,
                                                                             'date': date}))

