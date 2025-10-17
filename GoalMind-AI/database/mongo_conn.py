from flask_pymongo import PyMongo

mongo = PyMongo()

username = "shared_user"
pswd= "Ws5GnoquZHBvmoT6"

def init_app(app):
    app.config["MONGO_URI"] = f"mongodb+srv://{username}:{pswd}@database.3vr51dn.mongodb.net/data"
    mongo.init_app(app)
    return mongo