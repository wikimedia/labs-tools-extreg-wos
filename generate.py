#!/usr/bin/env python3

import datetime
import json
import os
import phabricator
import redis
import requests
import subprocess
import sys

with open('config.json') as f:
    conf = json.load(f)

ON_LABS = os.environ.get('INSTANCEPROJECT') == 'tools'
cache = redis.Redis(host='tools-redis' if ON_LABS else 'localhost')
phab = phabricator.Phabricator(conf['PHAB_HOST'], conf['PHAB_USER'], conf['PHAB_CERT'])

MW_DIR = '/data/project/extreg-wos/src' if ON_LABS else '/home/km/projects/vagrant/mediawiki'
WMF_TRACKING = 87875
OUTPUT_DIR = '/data/project/extreg-wos/public_html/' if ON_LABS else ''
PATCH_TO_REVIEW = 'PHID-PROJ-onnxucoedheq3jevknyr'
EASY = 'PHID-PROJ-2iftynis5nwxv3rpizpe'

def get_all_things(thing):
    ext_dir = os.path.join(MW_DIR, thing)
    return sorted(
        os.path.join(ext_dir, path)
        for path in os.listdir(ext_dir)
        if not path.startswith('.') and os.path.isdir(os.path.join(ext_dir, path))
    )


def get_archived():
    found = cache.get('extreg-archived')
    if found:
        return set(json.loads(found.decode()))
    data = set()
    r = requests.get('https://www.mediawiki.org/w/api.php?action=query&list=categorymembers&cmtitle=Category:Archived%20extensions&cmlimit=max&format=json')
    resp = r.json()
    for info in resp['query']['categorymembers']:
        if info['ns'] == 102:
            data.add(info['title'].split(':', 1)[1])
    cache.set('extreg-archived', json.dumps(list(data)), 60*60)
    return data


def get_bugs():
    found = cache.get('extreg-sos2')
    if found:
        return json.loads(found.decode())
    data = {}
    blocker_info = phab.request('maniphest.info', {'task_id': WMF_TRACKING})
    for phid in blocker_info['dependsOnTaskPHIDs']:
        phid_info = phab.request('phid.query', {'phids': [phid]})[phid]
        patch_to_review = False
        easy = False
        if phid_info['status'] != 'closed':
            maniphest_info = phab.request('maniphest.info', {
                'task_id': int(phid_info['name'][1:])
            })
            patch_to_review = PATCH_TO_REVIEW in maniphest_info['projectPHIDs']
            easy = EASY in maniphest_info['projectPHIDs']
        try:
            ext_name = phid_info['fullName'].split('Convert ', 1)[1].split('to use', 1)[0].strip()
            ext_name = ext_name.split('extension', 1)[0].strip()
        except IndexError:
            continue
        data[ext_name] = {
            'task_id': phid_info['name'],
            'review': patch_to_review,
            'easy': easy,
        }

    cache.set('extreg-sos1', json.dumps(data), 60*60)
    return data


def build_html(data):
    total = len(data)
    converted = sum(1 for info in data.values() if info['converted'])
    print(converted/total)
    percent = '{:.2f}'.format(converted/total*100) + '%'
    superpowers = converted/total >= 0.5
    s_text = 'superpowers' if superpowers else 'sadness'
    title = 'Extension registration wall of {s_text}'.format(s_text=s_text)
    excite = '!' if superpowers else ' :('
    print(percent)
    text = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<link rel="stylesheet" type="text/css" href="wos.css">
</head>
<body>
<h1>{title}{excite}</h1>
<p id="percentage">{converted}/{total} - {percent}</p>

<p>
In MediaWiki 1.25, a new system of loading extensions was introduced, called extension registration. Documentation
is available on <a href="https://www.mediawiki.org/wiki/Manual:Extension_registration">mediawiki.org</a>.
<br />
This tracks the conversion of extensions to the new system. Once over 50% of extensions are converted, the page name
will automatically change to "wall of superpowers!".
<br />
<small>This page should update hourly. Inspired by the <a href="http://python3wos.appspot.com/">Python 3 Wall of Superpowers</a>.</small>
</p>

<table>
    <tr>
        <th>Extension/Skin</th>
        <th>Converted?</th>
        <th>Bug</th>
        <th title="manifest_version">Version</th>
    </tr>
""".format(converted=converted, total=total, percent=percent, title=title, excite=excite)

    for name in sorted(data):
        converted_class = 'no'
        converted_text = 'No'
        easy_text = ''
        if data[name]['converted']:
            converted_class = 'yes'
            converted_text = data[name].get('msg', 'Yes')
        elif data[name].get('review'):
            converted_class = 'ptr'
            converted_text = 'Patch to review'

        if data[name].get('easy'):
            easy_text = ' (easy!)'

        if data['manifest_version']:
            mv = '<td>{}</td>'.format(data['manifest_version'])
        elif data[name]['converted']:
            mv = '<td class="mv-missing">Missing</td>'
        else:
            # Not yet converted
            mv = '<td></td>'
        text += """
    <tr class={classname}>
        <td>{name}</td>
        <td>{converted}</td>
        <td><a href="https://phabricator.wikimedia.org/{bug}">{bug}</a>{easy}</td>
        {mv}
    </tr>
""".format(name=name, converted=converted_text, classname=converted_class, bug=data[name].get('bug', ''), easy=easy_text, mv=mv)

    text += """
</table>
<p>Generated: {generated}</p>
</body></html>
""".format(generated=datetime.datetime.now())

    with open(OUTPUT_DIR + 'index.html', 'w') as f:
        f.write(text)
    with open(OUTPUT_DIR + 'data.json', 'w') as f:
        json.dump(data, f)
    toolinfo = """{{
    "name" : "extreg-wos",
    "title" : "{title}",
    "description" : "Table showing the progress of extension registration through MediaWiki extensions.",
    "url" : "https://tools.wmflabs.org/extreg-wos/",
    "keywords" : "MediaWiki",
    "author" : "Legoktm",
    "repository" : "https://github.com/wikimedia/labs-tools-extreg-wos"
}}
""".format(title=title)
    with open(OUTPUT_DIR + 'toolinfo.json', 'w') as f:
        f.write(toolinfo)


def git_update(thing):
    cwd = os.getcwd()
    os.chdir(os.path.join(MW_DIR, thing))
    subprocess.check_call(['git', 'pull'])
    try:
        subprocess.check_call(['git', 'submodule', 'update'])
    except subprocess.CalledProcessError:
        pass
    os.chdir(cwd)


def main():
    data = {}
    bugs = get_bugs()
    archived = get_archived()
    for thing in ('extensions', 'skins'):
        if '--no-update' not in sys.argv:
            git_update(thing)
        for path in get_all_things(thing):
            name = path.rsplit('/', 1)[1]
            if name in archived:
                continue
            json_fname = os.path.join(path, '%s.json' % thing[:-1])
            converted = os.path.isfile(json_fname)
            data[name] = {
                'path': path,
                'type': thing,
                'converted': converted,
                'manifest_version': False
            }
            if converted:
                try:
                    with open(json_fname) as f:
                        json_data = json.load(f)
                        data[name]['manifest_version'] = json_data.get('manifest_version', False)
                except ValueError:
                    pass
            php_entrypoint = os.path.join(path, '%s.php' % name)
            if converted and os.path.isfile(php_entrypoint):
                with open(php_entrypoint) as f_php:
                    try:
                        if 'wfLoad%s' % thing[:-1].title() in f_php.read():
                            data[name]['msg'] = 'Yes'
                        else:
                            data[name]['msg'] = 'Yes (duplicated)'
                    except UnicodeDecodeError:
                        # ???
                        data[name]['msg'] = 'Yes'
            if name in bugs:
                bug_info = bugs.pop(name)
                data[name]['bug'] = bug_info['task_id']
                data[name]['review'] = bug_info['review']
                data[name]['easy'] = bug_info['easy']

    for name, info in data.items():
        if info['converted']:
            print(name)

    build_html(data)
    print(bugs)

if __name__ == '__main__':
    main()
