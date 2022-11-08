#!flask/bin/python
from flask import Flask, jsonify
import os
from kg_generator.semantify import semantify
import requests

app = Flask(__name__)

@app.route('/')
def index():
    return "Welcome to the Rdf Graph Service"

@app.route('/graph_creation/<path:remove_duplicate>', methods=['GET','POST'])
def rdfgraph(remove_duplicate):
	if semantify(remove_duplicate):
		return "Done"

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=4000)