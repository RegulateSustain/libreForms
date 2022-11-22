""" 
mongo.py: creates a class for managing MongoDB form backends 

This script defines a class for managing a MongoDB database backend,
which is the default form datastore in the base application.

"""

__name__ = "app.mongo"
__author__ = "Sig Janoska-Bedi"
__credits__ = ["Sig Janoska-Bedi",]
__version__ = "1.0"
__license__ = "AGPL-3.0"
__maintainer__ = "Sig Janoska-Bedi"
__email__ = "signe@atreeus.com"


class MongoDB:
    def __init__(self, user='root', host='localhost', port=27017, dbpw=None):
        from pymongo import MongoClient
        import datetime, os

        # read database password file, if it exists
        if os.path.exists ("mongodb_creds"):
            with open("mongodb_creds", "r+") as f:
                mongodb_creds = f.read().strip()
        elif dbpw:  
            pass
        else:
            mongodb_creds=None

        conn = MongoClient(f'mongodb://{host}:{dbpw}@{host}:{str(port)}/')
        self.client = MongoClient(host, port)
        self.db = self.client['libreforms']

    def write_document_to_collection(self, data, collection_name, 
                                                    reporter=None,
                                                    # the `modifications` kwarg expects a truth statement
                                                    # presuming that `data` will just be a slice of changed data
                                                    modification=False):
        import datetime
        from bson.objectid import ObjectId

        collection = self.db[collection_name]
        data['Timestamp'] = str(datetime.datetime.utcnow())
        data['Reporter'] = str(reporter) if reporter else None
        
        # here we define the behavior of the `Journal` metadata field 
        if not modification:
            data['Journal'] = { data['Timestamp']: {
                                                    'Reporter': data['Reporter'],
                                                    'initial_submission': True}
                                                    }
            collection.insert_one(data).inserted_id

        else:
            journal_data = data.copy()
            del journal_data['_id']
            # data['Journal'] = 0
            ## Right now, this is overwriting the journal -- we should change this
            data['Journal'][data['Timestamp']] =  dict(journal_data)
            collection.update_one({'_id': ObjectId(data['_id'])}, { "$set": journal_data}, upsert=False)



    def read_documents_from_collection(self, collection_name):
        collection = self.db[collection_name]
        return collection.find()

