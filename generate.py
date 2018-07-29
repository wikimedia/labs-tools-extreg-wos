#!/usr/bin/env python3
"""
extreg-wos creates a list of extensions and their status on conversion
Copyright (C) 2015-2018 Kunal Mehta <legoktm@member.fsf.org>
Copyright (C) 2016 Reedy <reedy@wikimedia.org>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
import datetime
import json
import os
import phabricator
import requests
import toolforge
import wikimediaci_utils as ci

toolforge.set_user_agent('extreg-wos')

with open('config.json') as f:
    conf = json.load(f)

ON_LABS = os.environ.get('INSTANCEPROJECT') == 'tools'
phab = phabricator.Phabricator(conf['PHAB_HOST'], conf['PHAB_USER'], conf['PHAB_CERT'])
s = requests.Session()

MW_DIR = '/data/project/extreg-wos/src' if ON_LABS else '/home/km/gerrit/mediawiki/core'
WMF_TRACKING = 87875
OTHER_TRACKING = 98668
OUTPUT_DIR = '/data/project/extreg-wos/public_html/' if ON_LABS else ''
PATCH_TO_REVIEW = 'PHID-PROJ-onnxucoedheq3jevknyr'
EASY = 'PHID-PROJ-2iftynis5nwxv3rpizpe'


def get_archived():
    data = set()
    cont = True
    params = {
        'action': 'query',
        'list': 'categorymembers',
        'cmtitle': 'Category:Archived extensions',
        'cmlimit': 'max',
        'format': 'json',
        'formatversion': 2
    }
    while cont:
        print(params)
        r = s.get('https://www.mediawiki.org/w/api.php', params=params)
        resp = r.json()
        for info in resp['query']['categorymembers']:
            if info['ns'] == 102:
                data.add(info['title'].split(':', 1)[1])
        if 'continue' in resp:
            params.update(resp['continue'])
            cont = True
        else:
            cont = False
    return data


def get_phab_file(gerrit_name, path):
    try:
        return json.loads(ci.get_gerrit_file(gerrit_name, path))
    except Exception:
        return None


def get_bugs(task_id, wmf):
    data = {}
    blocker_info = phab.request('maniphest.info', {'task_id': task_id})
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
            'wmf_deployed': wmf,
        }

    return data


def build_html(data):
    total = len(data)
    converted = sum(1 for info in data.values() if info['converted'])
    print(converted / total)
    percent = '{:.2f}'.format(converted / total * 100) + '%'
    superpowers = converted / total >= 0.5
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
<link rel="stylesheet" type="text/css" href="static/wos.css">
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
<small>This page should update hourly.
Inspired by the <a href="http://python3wos.appspot.com/">Python 3 Wall of Superpowers</a>.</small>
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
        wmf_deployed = ''
        if data[name]['converted']:
            converted_class = 'yes'
            converted_text = data[name].get('msg', 'Yes')
        elif data[name].get('review'):
            converted_class = 'ptr'
            converted_text = 'Patch to review'

        if data[name].get('easy'):
            easy_text = ' (easy!)'

        if data[name]['manifest_version']:
            mv = '<td>{}</td>'.format(data[name]['manifest_version'])
        elif data[name]['converted']:
            mv = '<td class="mv-missing">Missing</td>'
        else:
            # Not yet converted
            mv = '<td></td>'
        if data[name].get('wmf_deployed'):
            wmf_deployed = ' (WMF)'

        text += """
    <tr class={classname}>
        <td><a href="https://www.mediawiki.org/wiki/Extension:{name}">{name}</a></td>
        <td>{converted}</td>
        <td><a href="https://phabricator.wikimedia.org/{bug}">{bug}</a>{easy}{wmf}</td>
        {mv}
    </tr>
""".format(name=name, converted=converted_text,
           classname=converted_class, bug=data[name].get('bug', ''),
           easy=easy_text, mv=mv, wmf=wmf_deployed)

    text += """
</table>
<p>Report generated at {generated}</p>
<br />
Now available in <a href="data.json">JSON</a>!
</body></html>
""".format(generated=datetime.datetime.utcnow())

    return text


def main():
    data = {}
    bugs = get_bugs(WMF_TRACKING, True)
    bugs.update(get_bugs(OTHER_TRACKING, False))
    archived = get_archived()
    for repo in ci.mw_things_repos():
        thing = 'extensions' if repo.startswith('mediawiki/extensions') else 'skins'
        name = repo.split('/')[-1]
        print('Processing %s...' % name)
        if name in archived:
            continue
        ftype = thing[:-1] + '.json'
        json_data = get_phab_file('mediawiki/%s/%s' % (thing, name), ftype)
        converted = json_data is not None
        data[name] = {
            'type': thing,
            'converted': converted,
            'manifest_version': False
        }
        if converted:
            data[name]['manifest_version'] = json_data.get('manifest_version', False)
        if name in bugs:
            bug_info = bugs.pop(name)
            data[name]['bug'] = bug_info['task_id']
            data[name]['review'] = bug_info['review']
            data[name]['easy'] = bug_info['easy']
            data[name]['wmf_deployed'] = bug_info['wmf_deployed']

    for name, info in data.items():
        if info['converted']:
            print(name)

    with open(OUTPUT_DIR + 'data.json', 'w') as f:
        json.dump(data, f)

    print(bugs)


if __name__ == '__main__':
    main()
