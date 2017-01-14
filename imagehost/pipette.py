from flask import Flask, request, g, redirect, url_for, abort, \
                  render_template, send_from_directory
from flask_htmlmin import HTMLMIN as htmlmin
from flask_compressor import Compressor, CSSBundle, FileAsset
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug import secure_filename
from settings import *
from os.path import splitext, join, isfile
from sys import argv

import random
import sqlite3
import os
import string
import jinja2

app = Flask(__name__)
app.config.from_object(__name__)
app.config['MINIFY_PAGE'] = not DEBUG

# Rate limit default settings
limiter = Limiter(
    app,
    key_func=get_remote_address,
    global_limits=["3600 per hour"]
)

# Minification
htmlmin(app)
compressor = Compressor()
compressor.init_app(app)

# Bundles to be compressed
raleway = FileAsset(filename='css/raleway.css', processors=['cssmin'])
skeleton = FileAsset(filename='css/skeleton.css', processors=['cssmin'])
customcss = FileAsset(filename='css/custom.css', processors=['cssmin'])

cssBundle = CSSBundle('allCSS', assets=[raleway, skeleton, customcss],
                      processors=['cssmin'])
compressor.register_bundle(cssBundle)


def byteHumanise(num, suffix='B'):
    """Humanises bytes. Code thanks to SO user Sridhar Ratnakumar."""

    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti']:
        if abs(num) < 1024.0:
            return "%3.1f %s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f %s%s" % (num, 'Pi', suffix)


def getDirSize(dir):
    """Gets the size of a directory (flat)."""

    try:
        s = sum(os.path.getsize(f)
                for f in os.listdir(dir) if os.path.isfile(f))
    except:
        s = 0

    return byteHumanise(s)


def getMaxPossible():
    """Get the total possible number of combinations."""

    return sum([pow(61, s) for s in range(PATH_MINLENGTH, PATH_MAXLENGTH + 1)])


def getNoTaken(ext):
    """Check the number of total files with a certain extension are in the
    database."""

    db = sqlite3.connect(DATABASE)
    picNo = db.execute('SELECT COUNT(filename) FROM Pics WHERE filename ' +
                       'LIKE ?', [ext])

    return int(picNo.fetchall()[0][0])


def databaseFull():
    """Check whether a database is full."""

    db = sqlite3.connect(DATABASE)
    picNo = db.execute('SELECT COUNT(filename) FROM `Pics` GROUP BY `id`')

    return True if int(picNo[0]) >= getMaxPossible() else False


def hash(size):
    """Insecurely generates a random string of n size."""

    chooseFrom = string.ascii_uppercase + string.ascii_lowercase + \
        string.digits
    chars = [random.SystemRandom().choice(chooseFrom) for _ in range(size)]

    return str(''.join(chars))


def addApiKey():
    """Adds an API key to the api.keys file."""

    with open(APIKEY_FILE, "a") as f:
        key = hash(ENTROPY)
        f.write(key + '\n')

        return key


def okApiKey(apikey, verbose=DEBUG):
    """Returns True if API key is accepted."""

    open(APIKEY_FILE, 'a').close()
    with open(APIKEY_FILE, 'r') as f:
        if verbose:
            print("\nYour API key is: '" + apikey + "'\n")
        for j in [str(i.rstrip()) for i in f.readlines()]:
            if verbose:
                print("Testing: " + j)
            if str(j) == str(apikey):
                if verbose:
                    print("Okay API key!")
                return True
        if verbose:
            print("API key not in list! Failed.")
        return False


def allowedExtension(extension):
    """Make sure extension is in the ALLOWED_EXTENSIONS set."""

    extension = "." + extension

    return extension in ALLOWED_EXTENSIONS


def isUnique(filename):
    """Checks if a filename exists in the database."""

    db = sqlite3.connect(DATABASE)
    items = db.execute('SELECT filename FROM `Pics` WHERE filename == (?)',
                       [filename])

    if filename in items:
        db.close()
        return False

    db.close()
    return True


def addPic(filename):
    """Insert filename into database."""

    db = sqlite3.connect(DATABASE)
    db.execute('INSERT INTO `Pics` (filename) values (?)', [filename])
    db.commit()
    db.close()


def init():
    """(Re)initialises database file."""

    db = sqlite3.connect(DATABASE)
    with app.open_resource(SCHEMA, mode='r') as f:
        db.executescript(f.read())
    db.commit()
    db.close()


@app.errorhandler(503)
def forbidden(e):
    return render_template('502.html'), 502


@app.errorhandler(500)
def forbidden(e):
    return render_template('500.html'), 500


@app.errorhandler(404)
def notFound(e):
    return render_template('404.html'), 404


@app.errorhandler(403)
def forbidden(e):
    return render_template('403.html'), 403


@app.route('/', methods=['GET', 'POST'])
def uploadPic():
    if request.method == 'POST':
        file = request.files['file']
        apikey = request.form['apikey'].rstrip()
        extension = str(splitext(file.filename)[1].lower())

        if file and okApiKey(apikey) and allowedExtension(extension) or DEBUG:
            gettingFullWarning = False
            counter = 0
            while True:
                fn = hash(random.randint(PATH_MINLENGTH, PATH_MAXLENGTH))

                # Check that we're not getting too full.
                if counter >= TOO_MANY_COLLISIONS:
                    if not gettingFullWarning:
                        print("We are adding a file to a densely " +
                              "populated database. We will start to " +
                              "accept collisions once we're full.")
                        gettingFullWarning = True
                    elif databaseFull():
                        break

                # Check that fn doesn't already exist in the database.
                if isUnique(fn):
                    break

                counter -= 1

            # This will overwrite existing if required.
            file.save(join(UPLOAD_DIR, fn + extension))

            # Finally, add the URL to the db table.
            addPic(fn)

            return request.url_root + fn + extension

        # Bad file extension, no file, or bad API key.
        return "allowedExtension: " + str(allowedExtension(extension)) + ", okApiKey: " + str(okApiKey(apikey)) + ", file: " + str(file)
        abort(403)

    # If the user just tries to get to the site without a POST request:
    return render_template('base.html', hostname=request.url_root, me=WHOAMI,
                           desc=BASE_DESCRIPTION)


@app.route('/diagnostics')
def diagnostics():
    totalFilesPerExt = getMaxPossible()
    totalPossibleFiles = len(ALLOWED_EXTENSIONS)*totalFilesPerExt

    filesUsed = list()  # List of dicts with data to be passed to template.

    totalUsed = 0  # Cumulative sum of the total used files.

    for i in ALLOWED_EXTENSIONS:
        taken = getNoTaken(i)
        percent = '{0:.1f}%'.format(100.0*taken/totalFilesPerExt)

        totalUsed += taken

        filesUsed.append({"extension": i, "used": '{:,}'.format(taken),
                          "percent": percent,
                          "left": '{:,}'.format(totalFilesPerExt - taken),
                          "total": '{:,}'.format(totalFilesPerExt)})

    # Total calculations.
    percent = '{0:.1f}%'.format(100.0*totalUsed/totalPossibleFiles)

    filesUsed.append({"extension": "TOTAL",
                      "used": '{:,}'.format(totalUsed),
                      "percent": percent,
                      "left": '{:,}'.format(totalPossibleFiles - totalUsed),
                      "total": '{:,}'.format(totalPossibleFiles)})

    # Now, sort the files used so the type with the highest usage is first.
    filesUsed = sorted(filesUsed, key=lambda k: int(k['used']))

    # We also pass the size of the pics directory to diagnostics.
    dirSize = getDirSize(UPLOAD_DIR)

    return render_template('diagnostics.html', payload=filesUsed, me=WHOAMI,
                           desc=DIAG_DESCRIPTION, dirSize=dirSize)


@app.route('/<filename>')
def returnPic(filename):
    return send_from_directory(app.config['UPLOAD_DIR'],
                               secure_filename(filename))


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicons/favicon.ico',
                               mimetype='image/vnd.microsoft.icon')

if __name__ == '__main__':
    # If run with no cmdline args, just start the server.

    # Ensure database is initialised.
    if not isfile(DATABASE):
        with open(DATABASE, 'a') as f:
            init()

    """ Operations:
    - start: start pipette server.
    - newkey: generate new API key.
    - checkkey: verbosely checks if an API key is good.
    - restart: destroys all file references in database.
    """

    if len(argv) == 1:
        app.run(debug=DEBUG, host='0.0.0.0')
    elif len(argv) >= 2:
        if argv[1].lower() in ["start", "run", "runserver"]:
            app.run(debug=DEBUG, host='0.0.0.0')
        elif argv[1].lower() == "newkey":
            print("Your secret API key is: " + addApiKey())
        elif argv[1].lower() == "checkkey":
            print("Checking that your key is valid...")
            okApiKey(argv[2], True)

        elif argv[1] == "restart":
            if raw_input("Are you ABSOLUTELY sure? All files will be " +
                         "destroyed! Type 'yes' if you understand. ") == "yes":
                init()
                print("Restarted! Old files have not been purged.")
            else:
                print("Nothing was changed.")
        else:
            print("Your command was not recognised: " + argv[1:].join(" "))