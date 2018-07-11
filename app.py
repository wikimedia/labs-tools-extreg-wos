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

from flask import Flask, jsonify
import json
import os
import toolforge

import generate


app = Flask(__name__)
app.before_request(toolforge.redirect_to_https)

DATA_PATH = os.path.join(os.path.dirname(__file__), 'data.json')


def get_data():
    with open(DATA_PATH) as f:
        data = json.load(f)

    return data


@app.route('/toolinfo.json')
def toolinfo():
    return jsonify(
        name='extreg-wos',
        title='Extension registration wall of sadness',
        description='Table showing the progress of extension registration through MediaWiki extensions.',
        url='https://tools.wmflabs.org/extreg-wos/',
        keywords='MediaWiki',
        author='Legoktm',
        repository='https://phabricator.wikimedia.org/diffusion/TERO/'
    )


@app.route('/data.json')
def data():
    return jsonify(**get_data())


@app.route('/')
def main():
    data = get_data()
    return generate.build_html(data)


if __name__ == '__main__':
    app.run(debug=True)
