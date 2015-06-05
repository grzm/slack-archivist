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
from datetime import datetime
import codecs
import re

from docopt import docopt
import pystache
import yaml
from slackclient import SlackClient
from markdown import markdown
from mdx_gfm import GithubFlavoredMarkdownExtension

special_pat = re.compile(r"<(.*?)>")


def format_special(x, members, channels):
    xs = x.split('|', 2)
    if len(xs) == 2:
        label = xs[1]
    else:
        label = xs[0]
    if x[0] == '#':
        return '#' + channels[xs[0][1:]]['name']
    elif x[0] == '@':
        return '@' + members[xs[0][1:]]['name']
    elif x[0] == '!':
        return label
    else:
        return '[%s](%s)' % (label, xs[0])


def format_text(text, members, channels):
    text = re.sub(special_pat, lambda x: format_special(x.group(1), members, channels), text)
    return markdown(text, extensions=[GithubFlavoredMarkdownExtension()])


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

            if channel['is_archived']:
                print "is archived"
                continue

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

        renderer = pystache.Renderer(search_dirs='template')
        out_dir = arguments['<output_dir>']
        shutil.copy2('template/global.css', out_dir)
        today = datetime.today().strftime('%Y-%m-%d')

        with codecs.open(os.path.join(out_dir, 'index.html'), 'wb', 'utf-8') as f:
            f.write(renderer.render_path('template/index.mustache', {'channels': channels.values(), }))

        for channel in channels.values():
            p = os.path.join(out_dir, channel['name'])
            try:
                os.makedirs(p)
            except OSError:
                pass

        for log in glob('logs/*.txt'):
            date, _ = os.path.splitext(os.path.basename(log))
            # if date == today:
            #     continue
            data = defaultdict(list)
            with codecs.open(log, 'rb', 'utf-8') as f:
                for msg in f:
                    msg = json.loads(msg)
                    if ('subtype' in msg) or ('user' not in msg):
                        continue
                    user_id = msg['user']
                    msg['user'] = members[user_id]['name']
                    msg['avatar'] = members[user_id]['profile']['image_48']
                    msg['timestamp'] = datetime.fromtimestamp(float(msg['ts'])).strftime('%H:%M:%S')
                    msg['text'] = format_text(msg['text'], members, channels)
                    data[channels[msg['channel']]['name']].append(msg)

            for channel_name, msgs in data.iteritems():
                with codecs.open(os.path.join(out_dir, channel_name, date) + '.html', 'wb', 'utf-8') as f:
                    f.write(renderer.render_path('template/day.mustache', {'active_channel': channel_name,
                                                                           'channels': channels.values(),
                                                                           'messages': msgs,
                                                                           'date': date}))

            if date < today:
                shutil.move(log, os.path.join('backup/clojurians-log', os.path.basename(log)))

        for channel in channels.values():
            p = os.path.join(out_dir, channel['name'])
            dates = []
            g = glob(os.path.join(p, '????-??-??.html'))
            g.sort()
            for html in g:
                date, _ = os.path.splitext(os.path.basename(html))
                dates.append({'date': date})
            with codecs.open(os.path.join(p, 'index.html'), 'wb', 'utf-8') as f:
                f.write(renderer.render_path('template/channel-index.mustache', {'dates': dates,
                                                                                 'active_channel': channel['name']}))
