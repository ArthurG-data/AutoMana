from flaskr.factory import create_app

import os 
import configparser

config = configparser.ConfigParser()
config.read(os.path.abspath(os.path.join("config.ini")))

if __name__=="__main__":
    app = create_app()
    print('app created')
    app.config['DEBUG'] = True
    app.config['SECRET_KEY'] = 'dev'
    app.config['MONGO_URI'] = config['PROD']['DB_URI']

    app.run()