#!/usr/bin/python
from flask import Flask, request, g, redirect, url_for, abort, \
                  render_template, send_from_directory
from werkzeug import secure_filename
from os.path import splitext, join, isfile
from sys import argv
import random
import sqlite3
import os
import string

# Settings
DEBUG = True
UPLOAD_DIR = 'pics'
APIKEY_FILE = 'api.keys'
DATABASE = 'flaskgur.db'
SCHEMA = 'schema.sql'
ALLOWED_EXTENSIONS = set(["jpg", "png", "ico", "bmp", "txt", "md", "gifv",
                          "mp4", "gif", "webm", "mp3", "xml", "json", "csv"])

# Set the following to n where the number of unique images is sum from
# s=PATH_MAXLENGTH to PATH_MINLENGTH of 61^s where PATH_MINLENGTH subtracted
# from PATH_MAXLENGTH >= 0. The default settings of 2 and 4 respectively allow
# 14,076,543 different uploads.
PATH_MINLENGTH = 2
PATH_MAXLENGTH = 4

app = Flask(__name__)
app.config.from_object(__name__)


def hash(size):
    """Insecurely generates a random string of n size."""
    chooseFrom = string.ascii_uppercase + string.ascii_lowercase + \
                 string.digits
    chars = [random.SystemRandom().choice(chooseFrom) for _ in range(size)]

    return ''.join(chars)


def addApiKey():
    """Adds an API key to the api.keys file."""
    
    with open(APIKEY_FILE, "a") as f:
        key = hash(64)
        f.write(key)
        
        return key


def okApiKey(apikey):
    """Returns True if API key is accepted."""
    
    with open(APIKEY_FILE, 'a') as f:
        return True if apikey in f.readlines() else False


def allowedExtension(extension):
    """Make sure extension is in the ALLOWD_EXTENSIONS set."""
    return extension in ALLOWED_EXTENSIONS


def isUnique(filename):
    """Checks if a filename exists in the database."""
    
    items = g.db.execute('SELECT filename FROM `Pics` WHERE filename == (?)',
                         [filename])
    if filename in items:
        return False
    
    return True
    
    
def connect():
    """Connect to an SQLite database file."""
    return sqlite3.connect(app.config['DATABASE'])

 
def addPic(filename):
    """Insert filename into database."""
    g.db.execute('INSERT INTO `Pics` (filename) values (?)', [filename])
    g.db.commit()

    
def getDb():
    """Get a database connection."""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
    return db

    
def init():
    """Reinits database file."""
    with app.app_context():
        db = getDb()
        with app.open_resource(SCHEMA, mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()


@app.before_request
def startRequest():
    g.db = connect()


@app.teardown_request
def endRequest(exception):
    db = getattr(g, 'db', None)
    if db is not None:
        db.close()


@app.errorhandler(404)
def notFound(e):
    return render_template('404.html'), 404


@app.errorhandler(403)
def forbidden(e):
    return render_template('403.html'), 403


@app.route('/', methods=['GET','POST'])
def uploadPic():
    if request.method == 'POST':
        file = request.files['file']
        apikey = request.form['apikey']
        
        extension = splitext(file.filename)[1].lower()
            
        if file and okApiKey(apikey): # and allowedExtension(extension):
            while True:
                fn = hash(random.randint(PATH_MINLENGTH, PATH_MAXLENGTH))
            
                # Check that fn doesn't already exist in the database.
                if isUnique(fn):
                    break
            
            file.save(join(app.config['UPLOAD_DIR'], filename))
            
            # Finally, add the URL to the db table.
            addPic(filename)  
            
            return redirect(url_for('show_pic', filename=fn))
        else:  # Bad file extension or API key.
            abort(403)
    else:
        # If the user just tries to get to the site without a POST request:
        return render_template('base.html')


@app.route('/<filename>')
def returnPic(filename):
    """Displays the image requested, 404 if not found."""
    return send_from_directory(app.config['UPLOAD_DIR'],
                               secure_filename(filename))


if __name__ == '__main__':
    # If run with no cmdline args, just start the server.
    
    if not isfile(DATABASE):
        with open(DATABASE, 'a') as f:
            init()
    
    if len(argv) == 1:
        app.run(debug=DEBUG, host='0.0.0.0')
    elif len(argv) == 2:
        if argv[1].lower() == "start":
            app.run(debug=DEBUG, host='0.0.0.0')
        elif argv[1].lower() == "newkey":
            print("Your secret API key is: " + addApiKey())
        elif argv[1] == "restart":
            if raw_input("Are you ABSOLUTELY sure? All files will be " + \
                         "destroyed! Type 'yes' if you understand.") == "yes":
                init()
                print("Restarted! Old files have not been purged.")
            else:
                print("Nothing was changed.")
                
