import os
import re
import csv
import sys
import rdflib
from rdflib.plugins.sparql import prepareQuery
from configparser import ConfigParser, ExtendedInterpolation
import traceback
from concurrent.futures import ThreadPoolExecutor
import time
import pandas as pd
#from pyspark import *
from .functions import *
import tracemalloc

try:
	from triples_map import TriplesMap as tm
except:
	from .triples_map import TriplesMap as tm	

import tracemalloc
# Work in the rr:sqlQuery (change mapping parser query, add sqlite3 support, etc)
# Work in the "when subject is empty" thing (uuid.uuid4(), dependency graph over the ) 

global id_number
id_number = 0
global g_triples 
g_triples = {}
global number_triple
number_triple = 0
global triples
triples = []
global duplicate
duplicate = "yes"
global start_time
start_time = time.time()
global join_table 
join_table = {}
global po_table
po_table = {}
global prefixes
prefixes = {}
global enrichment
enrichment = ""
global ignore
ignore = "yes"
global dic_table
dic_table = {}
global base
base = ""
global blank_message
blank_message = True
global general_predicates
general_predicates = {"http://www.w3.org/2000/01/rdf-schema#subClassOf":"",
						"http://www.w3.org/2002/07/owl#sameAs":"",
						"http://www.w3.org/2000/01/rdf-schema#seeAlso":"",
						"http://www.w3.org/2000/01/rdf-schema#subPropertyOf":""}

def release_PTT(triples_map,predicate_list):
	for po in triples_map.predicate_object_maps_list:
		if po.predicate_map.value in general_predicates:
			if po.predicate_map.value in predicate_list:
				predicate_list[po.predicate_map.value + "_" + po.object_map.value] -= 1
				if predicate_list[po.predicate_map.value + "_" + po.object_map.value] == 0:
					predicate_list.pop(po.predicate_map.value + "_" + po.object_map.value)
					resource = "<" + po.predicate_map.value + ">" + "_" + po.object_map.value
					if resource in dic_table:
						if dic_table[resource] in g_triples:
							g_triples.pop(dic_table[resource])
		else:
			if po.predicate_map.value in predicate_list:
				predicate_list[po.predicate_map.value] -= 1
				if predicate_list[po.predicate_map.value] == 0:
					predicate_list.pop(po.predicate_map.value)
					resource = "<" + po.predicate_map.value + ">"
					if resource in dic_table:
						if dic_table[resource] in g_triples:
							g_triples.pop(dic_table[resource])
	if triples_map.subject_map.rdf_class != None:
		for rdf_type in triples_map.subject_map.rdf_class:
			resource = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type" + "_" + "<{}>".format(rdf_type)
			if resource in predicate_list:
				predicate_list[resource] -= 1
				if predicate_list[resource] == 0:
					predicate_list.pop(resource)
					rdf_class = "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>" + "_" + "<{}>".format(rdf_type)
					if rdf_class in dic_table:
						if dic_table[rdf_class] in g_triples:
							g_triples.pop(dic_table[rdf_class])
	return predicate_list

def dictionary_table_update(resource):
	if resource not in dic_table:
		global id_number
		dic_table[resource] = base36encode(id_number)
		id_number += 1

def hash_update(parent_data, parent_subject, child_object,join_id):
	hash_table = {}
	for row in parent_data:
		if child_object.parent[0] in row.keys():
			if row[child_object.parent[0]] in hash_table:
				if duplicate == "yes":
					if parent_subject.subject_map.subject_mapping_type == "reference":
						value = string_substitution(parent_subject.subject_map.value, ".+", row, "object", ignore, parent_subject.iterator)
						if value != None:
							if "http" in value and "<" not in value:
								value = "<" + value[1:-1] + ">"
							elif "http" in value and "<" in value:
								value = value[1:-1] 
						if value not in hash_table[row[child_object.parent[0]]]:
							hash_table[row[child_object.parent[0]]].update({value : "object"})
					else:
						if string_substitution(parent_subject.subject_map.value, "{(.+?)}", row, "object", ignore, parent_subject.iterator) is not None:
							if "<" + string_substitution(parent_subject.subject_map.value, "{(.+?)}", row, "object", ignore, parent_subject.iterator) + ">" not in hash_table[row[child_object.parent[0]]]:
								hash_table[row[child_object.parent[0]]].update({"<" + string_substitution(parent_subject.subject_map.value, "{(.+?)}", row, "object", ignore, parent_subject.iterator) + ">" : "object"}) 
				else:
					if parent_subject.subject_map.subject_mapping_type == "reference":
						value = string_substitution(parent_subject.subject_map.value, ".+", row, "object", ignore)
						if "http" in value and "<" not in value:
							value = "<" + value[1:-1] + ">"
						elif "http" in value and "<" in value:
							value = value[1:-1] 
						hash_table[row[child_object.parent[0]]].update({value : "object"})
					else:
						if string_substitution(parent_subject.subject_map.value, "{(.+?)}", row, "object", ignore, parent_subject.iterator) is not None:
							hash_table[row[child_object.parent[0]]].update({"<" + string_substitution(parent_subject.subject_map.value, "{(.+?)}", row, "object", ignore, parent_subject.iterator) + ">" : "object"})

			else:
				if parent_subject.subject_map.subject_mapping_type == "reference":
					value = string_substitution(parent_subject.subject_map.value, ".+", row, "object", ignore, parent_subject.iterator)
					if value != None:
						if "http" in value and "<" not in value:
							value = "<" + value[1:-1] + ">"
						elif "http" in value and "<" in value:
							value = value[1:-1] 
					hash_table.update({row[child_object.parent[0]] : {value : "object"}}) 
				else:
					if string_substitution(parent_subject.subject_map.value, "{(.+?)}", row, "object", ignore, parent_subject.iterator) is not None:
						hash_table.update({row[child_object.parent[0]] : {"<" + string_substitution(parent_subject.subject_map.value, "{(.+?)}", row, "object", ignore, parent_subject.iterator) + ">" : "object"}})
	join_table[join_id].update(hash_table)

def hash_maker(parent_data, parent_subject, child_object):
	global blank_message
	hash_table = {}
	for row in parent_data:
		if child_object.parent[0] in row.keys():
			if row[child_object.parent[0]] in hash_table:
				if duplicate == "yes":
					if parent_subject.subject_map.subject_mapping_type == "reference":
						value = string_substitution(parent_subject.subject_map.value, ".+", row, "object", ignore, parent_subject.iterator)
						if value != None:
							if "http" in value and "<" not in value:
								value = "<" + value[1:-1] + ">"
							elif "http" in value and "<" in value:
								value = value[1:-1] 
						if value not in hash_table[row[child_object.parent[0]]]:
							hash_table[row[child_object.parent[0]]].update({value : "object"})
					else:
						if string_substitution(parent_subject.subject_map.value, "{(.+?)}", row, "object", ignore, parent_subject.iterator) != None:
							value = string_substitution(parent_subject.subject_map.value, "{(.+?)}", row, "object", ignore, parent_subject.iterator)
							if value != None:
								if parent_subject.subject_map.term_type != None:
									if "BlankNode" in parent_subject.subject_map.term_type:
										if "/" in value:
											value = "_:" + encode_char(value.replace("/","2F")).replace("%","")
											if "." in value:
												value = value.replace(".","2E")
											if blank_message:
												print("Incorrect format for Blank Nodes. \"/\" will be replace with \"2F\".")
												blank_message = False
										else:
											value = "_:" + encode_char(value).replace("%","")
											if "." in value:
												value = value.replace(".","2E")
								else:
									value = "<" + value + ">"
								hash_table[row[child_object.parent[0]]].update({value : "object"})
				else:
					if parent_subject.subject_map.subject_mapping_type == "reference":
						value = string_substitution(parent_subject.subject_map.value, ".+", row, "object", ignore, parent_subject.iterator)
						if "http" in value and "<" not in value:
							value = "<" + value[1:-1] + ">"
						elif "http" in value and "<" in value:
							value = value[1:-1] 
						hash_table[row[child_object.parent[0]]].update({value : "object"})
					else:
						value = string_substitution(parent_subject.subject_map.value, "{(.+?)}", row, "object", ignore, parent_subject.iterator)
						if value != None:
							if parent_subject.subject_map.term_type != None:
								if "BlankNode" in parent_subject.subject_map.term_type:
									if "/" in value:
										value = "_:" + encode_char(value.replace("/","2F")).replace("%","")
										if "." in value:
											value = value.replace(".","2E")
										if blank_message:
											print("Incorrect format for Blank Nodes. \"/\" will be replace with \"2F\".")
											blank_message = False
									else:
										value = "_:" + encode_char(value).replace("%","")
										if "." in value:
											value = value.replace(".","2E")
							else:
								value = "<" + value + ">"
							hash_table[row[child_object.parent[0]]].update({value : "object"})

			else:
				if parent_subject.subject_map.subject_mapping_type == "reference":
					value = string_substitution(parent_subject.subject_map.value, ".+", row, "object", ignore, parent_subject.iterator)
					if value != None:
						if "http" in value and "<" not in value:
							value = "<" + value[1:-1] + ">"
						elif "http" in value and "<" in value:
							value = value[1:-1] 
					hash_table.update({row[child_object.parent[0]] : {value : "object"}}) 
				else:
					value = string_substitution(parent_subject.subject_map.value, "{(.+?)}", row, "object", ignore, parent_subject.iterator)
					if value != None:
						if parent_subject.subject_map.term_type != None:
							if "BlankNode" in parent_subject.subject_map.term_type:
								if "/" in value:
									value = "_:" + encode_char(value.replace("/","2F")).replace("%","")
									if "." in value:
										value = value.replace(".","2E")
									if blank_message:
										print("Incorrect format for Blank Nodes. \"/\" will be replace with \"2F\".")
										blank_message = False
								else:
									value = "_:" + encode_char(value).replace("%","")
									if "." in value:
										value = value.replace(".","2E")
						else:
							value = "<" + value + ">"
						hash_table.update({row[child_object.parent[0]] : {value : "object"}})
	join_table.update({parent_subject.triples_map_id + "_" + child_object.child[0] : hash_table})

def hash_maker_list(parent_data, parent_subject, child_object):
	hash_table = {}
	global blank_message
	for row in parent_data:
		if sublist(child_object.parent,row.keys()):
			if child_list_value(child_object.parent,row) in hash_table:
				if duplicate == "yes":
					if parent_subject.subject_map.subject_mapping_type == "reference":
						value = string_substitution(parent_subject.subject_map.value, ".+", row, "object", ignore, parent_subject.iterator)
						if value != None:
							if "http" in value and "<" not in value:
								value = "<" + value[1:-1] + ">"
							elif "http" in value and "<" in value:
								value = value[1:-1] 
						hash_table[child_list_value(child_object.parent,row)].update({value : "object"})
					else:
						value = string_substitution(parent_subject.subject_map.value, "{(.+?)}", row, "object", ignore, parent_subject.iterator)
						if value != None:
							if parent_subject.subject_map.term_type != None:
								if "BlankNode" in parent_subject.subject_map.term_type:
									if "/" in value:
										value = "_:" + encode_char(value.replace("/","2F")).replace("%","")
										if "." in value:
											value = value.replace(".","2E")
										if blank_message:
											print("Incorrect format for Blank Nodes. \"/\" will be replace with \"2F\".")
											blank_message = False
									else:
										value = "_:" + encode_char(value).replace("%","")
										if "." in value:
											value = value.replace(".","2E")
							else:
								value = "<" + value + ">"
							hash_table[child_list_value(child_object.parent,row)].update({value: "object"})


				else:
					if parent_subject.subject_map.subject_mapping_type == "reference":
						value = string_substitution(parent_subject.subject_map.value, ".+", row, "object", ignore, parent_subject.iterator)
						if "http" in value and "<" not in value:
							value = "<" + value[1:-1] + ">"
						elif "http" in value and "<" in value:
							value = value[1:-1] 
						hash_table[child_list_value(child_object.parent,row)].update({value : "object"})
					else:
						value = string_substitution(parent_subject.subject_map.value, "{(.+?)}", row, "object", ignore, parent_subject.iterator)
						if value != None:
							if parent_subject.subject_map.term_type != None:
								if "BlankNode" in parent_subject.subject_map.term_type:
									if "/" in value:
										value = "_:" + encode_char(value.replace("/","2F")).replace("%","")
										if "." in value:
											value = value.replace(".","2E")
										if blank_message:
											print("Incorrect format for Blank Nodes. \"/\" will be replace with \"2F\".")
											blank_message = False
									else:
										value = "_:" + encode_char(value).replace("%","")
										if "." in value:
											value = value.replace(".","2E")
							else:
								value = "<" + value + ">"
							hash_table[child_list_value(child_object.parent,row)].update({value: "object"})

			else:
				if parent_subject.subject_map.subject_mapping_type == "reference":
					value = string_substitution(parent_subject.subject_map.value, ".+", row, "object", ignore, parent_subject.iterator)
					if value != None:
						if "http" in value and "<" not in value:
							value = "<" + value[1:-1] + ">"
						elif "http" in value and "<" in value:
							value = value[1:-1] 
					hash_table.update({child_list_value(child_object.parent,row) : {value : "object"}}) 
				else:
					value = string_substitution(parent_subject.subject_map.value, "{(.+?)}", row, "object", ignore, parent_subject.iterator)
					if value != None:
						if parent_subject.subject_map.term_type != None:
							if "BlankNode" in parent_subject.subject_map.term_type:
								if "/" in value:
									value = "_:" + encode_char(value.replace("/","2F")).replace("%","")
									if "." in value:
										value = value.replace(".","2E")
									if blank_message:
										print("Incorrect format for Blank Nodes. \"/\" will be replace with \"2F\".")
										blank_message = False
								else:
									value = "_:" + encode_char(value).replace("%","")
									if "." in value:
										value = value.replace(".","2E")
						else:
							value = "<" + value + ">"
						hash_table.update({child_list_value(child_object.parent,row) : {value : "object"}})
	join_table.update({parent_subject.triples_map_id + "_" + child_list(child_object.child) : hash_table})

def mapping_parser(mapping_file):

	"""
	(Private function, not accessible from outside this package)

	Takes a mapping file in Turtle (.ttl) or Notation3 (.n3) format and parses it into a list of
	TriplesMap objects (refer to TriplesMap.py file)

	Parameters
	----------
	mapping_file : string
		Path to the mapping file

	Returns
	-------
	A list of TriplesMap objects containing all the parsed rules from the original mapping file
	"""

	mapping_graph = rdflib.Graph()

	try:
		mapping_graph.parse(data=mapping_file, format='n3')
	except Exception as n3_mapping_parse_exception:
		print(n3_mapping_parse_exception)
		print('Could not parse {} as a mapping file'.format(mapping_file))
		print('Aborting...')
		sys.exit(1)

	mapping_query = """
		prefix rr: <http://www.w3.org/ns/r2rml#> 
		prefix rml: <http://semweb.mmlab.be/ns/rml#> 
		prefix ql: <http://semweb.mmlab.be/ns/ql#> 
		prefix d2rq: <http://www.wiwiss.fu-berlin.de/suhl/bizer/D2RQ/0.1#> 
		SELECT DISTINCT *
		WHERE {

	# Subject -------------------------------------------------------------------------
			?triples_map_id rml:logicalSource ?_source .
			OPTIONAL{?_source rml:source ?data_source .}
			OPTIONAL {?_source rml:referenceFormulation ?ref_form .}
			OPTIONAL { ?_source rml:iterator ?iterator . }
			OPTIONAL { ?_source rr:tableName ?tablename .}
			OPTIONAL { ?_source rml:query ?query .}

			?triples_map_id rr:subjectMap ?_subject_map .
			OPTIONAL {?_subject_map rr:template ?subject_template .}
			OPTIONAL {?_subject_map rml:reference ?subject_reference .}
			OPTIONAL {?_subject_map rr:constant ?subject_constant}
			OPTIONAL { ?_subject_map rr:class ?rdf_class . }
			OPTIONAL { ?_subject_map rr:termType ?termtype . }
			OPTIONAL { ?_subject_map rr:graph ?graph . }
			OPTIONAL { ?_subject_map rr:graphMap ?_graph_structure .
					   ?_graph_structure rr:constant ?graph . }
			OPTIONAL { ?_subject_map rr:graphMap ?_graph_structure .
					   ?_graph_structure rr:template ?graph . }		   

	# Predicate -----------------------------------------------------------------------
			OPTIONAL {
			?triples_map_id rr:predicateObjectMap ?_predicate_object_map .
			
			OPTIONAL {
				?triples_map_id rr:predicateObjectMap ?_predicate_object_map .
				?_predicate_object_map rr:predicateMap ?_predicate_map .
				?_predicate_map rr:constant ?predicate_constant .
			}
			OPTIONAL {
				?_predicate_object_map rr:predicateMap ?_predicate_map .
				?_predicate_map rr:template ?predicate_template .
			}
			OPTIONAL {
				?_predicate_object_map rr:predicateMap ?_predicate_map .
				?_predicate_map rml:reference ?predicate_reference .
			}
			OPTIONAL {
				?_predicate_object_map rr:predicate ?predicate_constant_shortcut .
			 }
			

	# Object --------------------------------------------------------------------------
			OPTIONAL {
				?_predicate_object_map rr:objectMap ?_object_map .
				?_object_map rr:constant ?object_constant .
				OPTIONAL {
					?_object_map rr:datatype ?object_datatype .
				}
			}
			OPTIONAL {
				?_predicate_object_map rr:objectMap ?_object_map .
				?_object_map rr:template ?object_template .
				OPTIONAL {?_object_map rr:termType ?term .}
				OPTIONAL {?_object_map rml:languageMap ?language_map.
						  ?language_map rml:reference ?language_value.}
				OPTIONAL {
					?_object_map rr:datatype ?object_datatype .
				}
			}
			OPTIONAL {
				?_predicate_object_map rr:objectMap ?_object_map .
				?_object_map rml:reference ?object_reference .
				OPTIONAL { ?_object_map rr:language ?language .}
				OPTIONAL {?_object_map rml:languageMap ?language_map.
						  ?language_map rml:reference ?language_value.}
				OPTIONAL {?_object_map rr:termType ?term .}
				OPTIONAL {
					?_object_map rr:datatype ?object_datatype .
				}
			}
			OPTIONAL {
				?_predicate_object_map rr:objectMap ?_object_map .
				?_object_map rr:parentTriplesMap ?object_parent_triples_map .
				OPTIONAL {
					?_object_map rr:joinCondition ?join_condition .
					?join_condition rr:child ?child_value;
								 rr:parent ?parent_value.
					OPTIONAL {?_object_map rr:termType ?term .}
				}
			}
			OPTIONAL {
				?_predicate_object_map rr:object ?object_constant_shortcut .
			}
			OPTIONAL {?_predicate_object_map rr:graph ?predicate_object_graph .}
			OPTIONAL { ?_predicate_object_map  rr:graphMap ?_graph_structure .
					   ?_graph_structure rr:constant ?predicate_object_graph  . }
			OPTIONAL { ?_predicate_object_map  rr:graphMap ?_graph_structure .
					   ?_graph_structure rr:template ?predicate_object_graph  . }	
			}
			OPTIONAL {
				?_source a d2rq:Database;
  				d2rq:jdbcDSN ?jdbcDSN; 
  				d2rq:jdbcDriver ?jdbcDriver; 
			    d2rq:username ?user;
			    d2rq:password ?password .
			}
		} """

	mapping_query_results = mapping_graph.query(mapping_query)
	triples_map_list = []


	for result_triples_map in mapping_query_results:
		triples_map_exists = False
		for triples_map in triples_map_list:
			triples_map_exists = triples_map_exists or (str(triples_map.triples_map_id) == str(result_triples_map.triples_map_id))
		
		if not triples_map_exists:
			if result_triples_map.subject_template != None:
				if result_triples_map.rdf_class is None:
					reference, condition = string_separetion(str(result_triples_map.subject_template))
					subject_map = tm.SubjectMap(str(result_triples_map.subject_template), condition, "template", [result_triples_map.rdf_class], result_triples_map.termtype, [result_triples_map.graph])
				else:
					reference, condition = string_separetion(str(result_triples_map.subject_template))
					subject_map = tm.SubjectMap(str(result_triples_map.subject_template), condition, "template", [str(result_triples_map.rdf_class)], result_triples_map.termtype, [result_triples_map.graph])
			elif result_triples_map.subject_reference != None:
				if result_triples_map.rdf_class is None:
					reference, condition = string_separetion(str(result_triples_map.subject_reference))
					subject_map = tm.SubjectMap(str(result_triples_map.subject_reference), condition, "reference", [result_triples_map.rdf_class], result_triples_map.termtype, [result_triples_map.graph])
				else:
					reference, condition = string_separetion(str(result_triples_map.subject_reference))
					subject_map = tm.SubjectMap(str(result_triples_map.subject_reference), condition, "reference", [str(result_triples_map.rdf_class)], result_triples_map.termtype, [result_triples_map.graph])
			elif result_triples_map.subject_constant != None:
				if result_triples_map.rdf_class is None:
					reference, condition = string_separetion(str(result_triples_map.subject_constant))
					subject_map = tm.SubjectMap(str(result_triples_map.subject_constant), condition, "constant", [result_triples_map.rdf_class], result_triples_map.termtype, [result_triples_map.graph])
				else:
					reference, condition = string_separetion(str(result_triples_map.subject_constant))
					subject_map = tm.SubjectMap(str(result_triples_map.subject_constant), condition, "constant", [str(result_triples_map.rdf_class)], result_triples_map.termtype, [result_triples_map.graph])
				
			mapping_query_prepared = prepareQuery(mapping_query)


			mapping_query_prepared_results = mapping_graph.query(mapping_query_prepared, initBindings={'triples_map_id': result_triples_map.triples_map_id})

			join_predicate = {}
			predicate_object_maps_list = []
			predicate_object_graph = {}
			for result_predicate_object_map in mapping_query_prepared_results:
				join = True
				if result_predicate_object_map.predicate_constant != None:
					predicate_map = tm.PredicateMap("constant", str(result_predicate_object_map.predicate_constant), "")
					predicate_object_graph[str(result_predicate_object_map.predicate_constant)] = result_triples_map.predicate_object_graph
				elif result_predicate_object_map.predicate_constant_shortcut != None:
					predicate_map = tm.PredicateMap("constant shortcut", str(result_predicate_object_map.predicate_constant_shortcut), "")
					predicate_object_graph[str(result_predicate_object_map.predicate_constant_shortcut)] = result_triples_map.predicate_object_graph
				elif result_predicate_object_map.predicate_template != None:
					template, condition = string_separetion(str(result_predicate_object_map.predicate_template))
					predicate_map = tm.PredicateMap("template", template, condition)
				elif result_predicate_object_map.predicate_reference != None:
					reference, condition = string_separetion(str(result_predicate_object_map.predicate_reference))
					predicate_map = tm.PredicateMap("reference", reference, condition)
				else:
					predicate_map = tm.PredicateMap("None", "None", "None")

				if result_predicate_object_map.object_constant != None:
					object_map = tm.ObjectMap("constant", str(result_predicate_object_map.object_constant), str(result_predicate_object_map.object_datatype), "None", "None", result_predicate_object_map.term, result_predicate_object_map.language,result_predicate_object_map.language_value)
				elif result_predicate_object_map.object_template != None:
					object_map = tm.ObjectMap("template", str(result_predicate_object_map.object_template), str(result_predicate_object_map.object_datatype), "None", "None", result_predicate_object_map.term, result_predicate_object_map.language,result_predicate_object_map.language_value)
				elif result_predicate_object_map.object_reference != None:
					object_map = tm.ObjectMap("reference", str(result_predicate_object_map.object_reference), str(result_predicate_object_map.object_datatype), "None", "None", result_predicate_object_map.term, result_predicate_object_map.language,result_predicate_object_map.language_value)
				elif result_predicate_object_map.object_parent_triples_map != None:
					if predicate_map.value + " " + str(result_predicate_object_map.object_parent_triples_map) not in join_predicate:
						join_predicate[predicate_map.value + " " + str(result_predicate_object_map.object_parent_triples_map)] = {"predicate":predicate_map, "childs":[str(result_predicate_object_map.child_value)], "parents":[str(result_predicate_object_map.parent_value)], "triples_map":str(result_predicate_object_map.object_parent_triples_map)}
					else:
						join_predicate[predicate_map.value + " " + str(result_predicate_object_map.object_parent_triples_map)]["childs"].append(str(result_predicate_object_map.child_value))
						join_predicate[predicate_map.value + " " + str(result_predicate_object_map.object_parent_triples_map)]["parents"].append(str(result_predicate_object_map.parent_value))
					join = False
				elif result_predicate_object_map.object_constant_shortcut != None:
					object_map = tm.ObjectMap("constant shortcut", str(result_predicate_object_map.object_constant_shortcut), "None", "None", "None", result_predicate_object_map.term, result_predicate_object_map.language,result_predicate_object_map.language_value)
				else:
					object_map = tm.ObjectMap("None", "None", "None", "None", "None", "None", "None", "None")
				if join:
					predicate_object_maps_list += [tm.PredicateObjectMap(predicate_map, object_map,predicate_object_graph)]
				join = True
			if join_predicate:
				for jp in join_predicate.keys():
					object_map = tm.ObjectMap("parent triples map", join_predicate[jp]["triples_map"], str(result_predicate_object_map.object_datatype), join_predicate[jp]["childs"], join_predicate[jp]["parents"],result_predicate_object_map.term, result_predicate_object_map.language,result_predicate_object_map.language_value)
					predicate_object_maps_list += [tm.PredicateObjectMap(join_predicate[jp]["predicate"], object_map,predicate_object_graph)]

			current_triples_map = tm.TriplesMap(str(result_triples_map.triples_map_id), str(result_triples_map.data_source), subject_map, predicate_object_maps_list, ref_form=str(result_triples_map.ref_form), iterator=str(result_triples_map.iterator), tablename=str(result_triples_map.tablename), query=str(result_triples_map.query))
			triples_map_list += [current_triples_map]

		else:
			for triples_map in triples_map_list:
				if str(triples_map.triples_map_id) == str(result_triples_map.triples_map_id):
					if result_triples_map.rdf_class not in triples_map.subject_map.rdf_class:
						triples_map.subject_map.rdf_class.append(result_triples_map.rdf_class)
					if result_triples_map.graph not in triples_map.subject_map.graph:
						triples_map.graph.append(result_triples_map.graph)

	return triples_map_list

def semantify_file(triples_map, triples_map_list, delimiter, data):

	object_list = []
	kg = ""
	no_update = True
	global blank_message
	print("TM:",triples_map.triples_map_name)
	for row in data:
		if triples_map.subject_map.subject_mapping_type == "template":
			subject_value = string_substitution(triples_map.subject_map.value, "{(.+?)}", row, "subject", ignore, triples_map.iterator)	
			if triples_map.subject_map.term_type is None:
				if triples_map.subject_map.condition == "":

					try:
						subject = "<" + subject_value + ">"
					except:
						subject = None

				else:
				#	field, condition = condition_separetor(triples_map.subject_map.condition)
				#	if row[field] == condition:
					try:
						subject = "<" + subject_value  + ">"
					except:
						subject = None 
			else:
				if "IRI" in triples_map.subject_map.term_type:
					subject_value = string_substitution(triples_map.subject_map.value, "{(.+?)}", row, "subject", ignore, triples_map.iterator)
					if triples_map.subject_map.condition == "":

						try:
							if "http" not in subject_value:
								subject = "<" + base + subject_value + ">"
							else:
								subject = "<" + encode_char(subject_value) + ">"
						except:
							subject = None

					else:
					#	field, condition = condition_separetor(triples_map.subject_map.condition)
					#	if row[field] == condition:
						try:
							if "http" not in subject_value:
								subject = subject = "<" + base + subject_value + ">"
							else:
								subject = "<" + subject_value + ">"
						except:
							subject = None 

				elif "BlankNode" in triples_map.subject_map.term_type:
					if triples_map.subject_map.condition == "":
						try:
							if "/" in subject_value:
								subject  = "_:" + encode_char(subject_value.replace("/","2F")).replace("%","")
								if "." in subject:
									subject = subject.replace(".","2E")
								if blank_message:
									print("Incorrect format for Blank Nodes. \"/\" will be replace with \"2F\".")
									blank_message = False
							else:
								subject = "_:" + encode_char(subject_value).replace("%","")
								if "." in subject:
									subject = subject.replace(".","2E")
						except:
							subject = None

					else:
					#	field, condition = condition_separetor(triples_map.subject_map.condition)
					#	if row[field] == condition:
						try:
							subject = "_:" + subject_value  
						except:
							subject = None
				elif "Literal" in triples_map.subject_map.term_type:
					subject = None			
				else:
					if triples_map.subject_map.condition == "":

						try:
							subject = "<" + subject_value + ">"
						except:
							subject = None

					else:
					#	field, condition = condition_separetor(triples_map.subject_map.condition)
					#	if row[field] == condition:
						try:
							subject = "<" + subject_value + ">"
						except:
							subject = None 
		elif "reference" in triples_map.subject_map.subject_mapping_type:
			subject_value = string_substitution(triples_map.subject_map.value, ".+", row, "subject",ignore , triples_map.iterator)
			if subject_value != None:
				subject_value = subject_value[1:-1]
				if triples_map.subject_map.condition == "":
					if " " not in subject_value:
						if "http" not in subject_value:
							subject = "<" + base + subject_value + ">"
						else:
							subject = "<" + subject_value + ">"
					else:
						subject = None

			else:
			#	field, condition = condition_separetor(triples_map.subject_map.condition)
			#	if row[field] == condition:
				try:
					if "http" not in subject_value:
						subject = "<" + base + subject_value + ">"
					else:
						subject = "<" + subject_value + ">"
				except:
					subject = None

		elif "constant" in triples_map.subject_map.subject_mapping_type:
			subject = "<" + subject_value + ">"

		else:
			if triples_map.subject_map.condition == "":

				try:
					subject = "\"" + triples_map.subject_map.value + "\""
				except:
					subject = None

			else:
			#	field, condition = condition_separetor(triples_map.subject_map.condition)
			#	if row[field] == condition:
				try:
					subject = "\"" + triples_map.subject_map.value + "\""
				except:
					subject = None


		if triples_map.subject_map.rdf_class != None and subject != None:
			predicate = "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>"
			for rdf_class in triples_map.subject_map.rdf_class:
				if rdf_class != None:
					obj = "<{}>".format(rdf_class)
					rdf_type = subject + " " + predicate + " " + obj + ".\n"
					for graph in triples_map.subject_map.graph:
						if graph != None and "defaultGraph" not in graph:
							if "{" in graph:	
								rdf_type = rdf_type[:-2] + " <" + string_substitution(graph, "{(.+?)}", row, "subject",ignore, triples_map.iterator) + "> .\n"
								dictionary_table_update("<" + string_substitution(graph, "{(.+?)}", row, "subject",ignore, triples_map.iterator) + ">")
							else:
								rdf_type = rdf_type[:-2] + " <" + graph + "> .\n"
								dictionary_table_update("<" + graph + ">")
					if duplicate == "yes":
						dictionary_table_update(subject)
						dictionary_table_update(obj)
						dictionary_table_update(predicate + "_" + obj)
						if dic_table[predicate + "_" + obj] not in g_triples:
							kg += rdf_type
							g_triples.update({dic_table[predicate  + "_" + obj ] : {dic_table[subject] + "_" + dic_table[obj]: ""}})
						elif dic_table[subject] + "_" + dic_table[obj] not in g_triples[dic_table[predicate + "_" + obj]]:
							kg += rdf_type
							g_triples[dic_table[predicate + "_" + obj]].update({dic_table[subject] + "_" + dic_table[obj] : ""})
						else:
							duplicate_type = True
					else:
						kg += rdf_type

		
		for predicate_object_map in triples_map.predicate_object_maps_list:
			if predicate_object_map.predicate_map.mapping_type == "constant" or predicate_object_map.predicate_map.mapping_type == "constant shortcut":
				predicate = "<" + predicate_object_map.predicate_map.value + ">"
			elif predicate_object_map.predicate_map.mapping_type == "template":
				if predicate_object_map.predicate_map.condition != "":
						#field, condition = condition_separetor(predicate_object_map.predicate_map.condition)
						#if row[field] == condition:
						try:
							predicate = "<" + string_substitution(predicate_object_map.predicate_map.value, "{(.+?)}", row, "predicate",ignore, triples_map.iterator) + ">"
						except:
							predicate = None
						#else:
						#	predicate = None
				else:
					try:
						predicate = "<" + string_substitution(predicate_object_map.predicate_map.value, "{(.+?)}", row, "predicate",ignore, triples_map.iterator) + ">"
					except:
						predicate = None
			elif predicate_object_map.predicate_map.mapping_type == "reference":
				if predicate_object_map.predicate_map.condition != "":
					#field, condition = condition_separetor(predicate_object_map.predicate_map.condition)
					#if row[field] == condition:
					predicate = string_substitution(predicate_object_map.predicate_map.value, ".+", row, "predicate",ignore, triples_map.iterator)
					#else:
					#	predicate = None
				else:
					predicate = string_substitution(predicate_object_map.predicate_map.value, ".+", row, "predicate",ignore, triples_map.iterator)
				predicate = "<" + predicate[1:-1] + ">"
			else:
				predicate = None

			if predicate_object_map.object_map.mapping_type == "constant" or predicate_object_map.object_map.mapping_type == "constant shortcut":
				if "/" in predicate_object_map.object_map.value:
					object = "<" + predicate_object_map.object_map.value + ">"
				else:
					object = "\"" + predicate_object_map.object_map.value + "\""
				if predicate_object_map.object_map.datatype != None:
					object = "\"" + object[1:-1] + "\"" + "^^<{}>".format(predicate_object_map.object_map.datatype)
			elif predicate_object_map.object_map.mapping_type == "template":
				try:
					if predicate_object_map.object_map.term is None:
						object = "<" + string_substitution(predicate_object_map.object_map.value, "{(.+?)}", row, "object",ignore, triples_map.iterator) + ">"
					elif "IRI" in predicate_object_map.object_map.term:
						object = "<" + string_substitution(predicate_object_map.object_map.value, "{(.+?)}", row, "object",ignore, triples_map.iterator) + ">"
					elif "BlankNode" in predicate_object_map.object_map.term:
						object = "_:" + string_substitution(predicate_object_map.object_map.value, "{(.+?)}", row, "object",ignore, triples_map.iterator)
						if "/" in object:
							object  = object.replace("/","2F")
							if blank_message:
								print("Incorrect format for Blank Nodes. \"/\" will be replace with \"2F\".")
								blank_message = False
						if "." in object:
							object = object.replace(".","2E")
						object = encode_char(object)
					else:
						object = "\"" + string_substitution(predicate_object_map.object_map.value, "{(.+?)}", row, "object",ignore, triples_map.iterator) + "\""
						if predicate_object_map.object_map.datatype != None:
							object = "\"" + object[1:-1] + "\"" + "^^<{}>".format(predicate_object_map.object_map.datatype)
						elif predicate_object_map.object_map.language != None:
							if "spanish" in predicate_object_map.object_map.language or "es" in predicate_object_map.object_map.language :
								object += "@es"
							elif "english" in predicate_object_map.object_map.language or "en" in predicate_object_map.object_map.language :
								object += "@en"
							elif len(predicate_object_map.object_map.language) == 2:
								object += "@"+predicate_object_map.object_map.language
						elif predicate_object_map.object_map.language_map != None:
							lang = string_substitution(predicate_object_map.object_map.language_map, ".+", row, "object",ignore, triples_map.iterator)
							if lang != None:
								object += "@" + string_substitution(predicate_object_map.object_map.language_map, ".+", row, "object",ignore, triples_map.iterator)[1:-1]  
				except TypeError:
					object = None
			elif predicate_object_map.object_map.mapping_type == "reference":
				object = string_substitution(predicate_object_map.object_map.value, ".+", row, "object",ignore, triples_map.iterator)
				if object != None:
					if "\\" in object[1:-1]:
						object = "\"" + object[1:-1].replace("\\","\\\\") + "\""
					if "'" in object[1:-1]:
						object = "\"" + object[1:-1].replace("'","\\\\'") + "\""
					if "\n" in object:
						object = object.replace("\n","\\n")
					if predicate_object_map.object_map.datatype != None:
						object = "\"" + object[1:-1] + "\"" + "^^<{}>".format(predicate_object_map.object_map.datatype)
					elif predicate_object_map.object_map.language != None:
						if "spanish" in predicate_object_map.object_map.language or "es" in predicate_object_map.object_map.language :
							object += "@es"
						elif "english" in predicate_object_map.object_map.language or "en" in predicate_object_map.object_map.language :
							object += "@en"
						elif len(predicate_object_map.object_map.language) == 2:
							object += "@"+predicate_object_map.object_map.language
					elif predicate_object_map.object_map.language_map != None:
						lang = string_substitution(predicate_object_map.object_map.language_map, ".+", row, "object",ignore, triples_map.iterator)
						if lang != None:
							object += "@"+ string_substitution(predicate_object_map.object_map.language_map, ".+", row, "object",ignore, triples_map.iterator)[1:-1]
					elif predicate_object_map.object_map.term != None:
						if "IRI" in predicate_object_map.object_map.term:
							if " " not in object:
								object = "\"" + object[1:-1].replace("\\\\'","'") + "\""
								object = "<" + encode_char(object[1:-1]) + ">"
							else:
								object = None
			elif predicate_object_map.object_map.mapping_type == "parent triples map":
				if subject != None:
					for triples_map_element in triples_map_list:
						if triples_map_element.triples_map_id == predicate_object_map.object_map.value:
							if triples_map_element.data_source != triples_map.data_source:
								if len(predicate_object_map.object_map.child) == 1:
									if (triples_map_element.triples_map_id + "_" + predicate_object_map.object_map.child[0]) not in join_table:
										if str(triples_map_element.file_format).lower() == "csv" or triples_map_element.file_format == "JSONPath":
											with open(str(triples_map_element.data_source), "r") as input_file_descriptor:
												if str(triples_map_element.file_format).lower() == "csv":
													reader = pd.read_csv(str(triples_map_element.data_source), dtype = str)#, encoding = "ISO-8859-1")
													reader = reader.where(pd.notnull(reader), None)
													reader = reader.drop_duplicates(keep ='first')
													data = reader.to_dict(orient='records')
													hash_maker(data, triples_map_element, predicate_object_map.object_map)
												else:
													data = json.load(input_file_descriptor)
													if triples_map_element.iterator:
														if triples_map_element.iterator != "None" and triples_map_element.iterator != "$.[*]":
															join_iterator(data, triples_map_element.iterator, triples_map_element, predicate_object_map.object_map)
														else:
															if isinstance(data, list):
																hash_maker(data, triples_map_element, predicate_object_map.object_map)
															elif len(data) < 2:
																hash_maker(data[list(data.keys())[0]], triples_map_element, predicate_object_map.object_map)
													else:
														if isinstance(data, list):
															hash_maker(data, triples_map_element, predicate_object_map.object_map)
														elif len(data) < 2:
															hash_maker(data[list(data.keys())[0]], triples_map_element, predicate_object_map.object_map)

										elif triples_map_element.file_format == "XPath":
											with open(str(triples_map_element.data_source), "r") as input_file_descriptor:
												child_tree = ET.parse(input_file_descriptor)
												child_root = child_tree.getroot()
												hash_maker_xml(child_root, triples_map_element, predicate_object_map.object_map)								
										else:
											database, query_list = translate_sql(triples_map)
											db = connector.connect(host=host, port=int(port), user=user, password=password)
											cursor = db.cursor(buffered=True)
											cursor.execute("use " + database)
											for query in query_list:
												cursor.execute(query)
											hash_maker_array(cursor, triples_map_element, predicate_object_map.object_map)

									if sublist(predicate_object_map.object_map.child,row.keys()):
										if child_list_value(predicate_object_map.object_map.child,row) in join_table[triples_map_element.triples_map_id + "_" + child_list(predicate_object_map.object_map.child)]:
											object_list = join_table[triples_map_element.triples_map_id + "_" + child_list(predicate_object_map.object_map.child)][child_list_value(predicate_object_map.object_map.child,row)]
										else:
											if no_update:
												if str(triples_map_element.file_format).lower() == "csv" or triples_map_element.file_format == "JSONPath":
													with open(str(triples_map_element.data_source), "r") as input_file_descriptor:
														if str(triples_map_element.file_format).lower() == "csv":
															reader = pd.read_csv(str(triples_map_element.data_source), dtype = str)#, encoding = "ISO-8859-1")
															reader = reader.where(pd.notnull(reader), None)
															reader = reader.drop_duplicates(keep ='first')
															data = reader.to_dict(orient='records')
															hash_update(data, triples_map_element, predicate_object_map.object_map, triples_map_element.triples_map_id + "_" + predicate_object_map.object_map.child[0])
														else:
															data = json.load(input_file_descriptor)
															if triples_map_element.iterator:
																if triples_map_element.iterator != "None" and triples_map_element.iterator != "$.[*]":
																	join_iterator(data, triples_map_element.iterator, triples_map_element, predicate_object_map.object_map)
																else:
																	if isinstance(data, list):
																		hash_maker(data, triples_map_element, predicate_object_map.object_map)
																	elif len(data) < 2:
																		hash_maker(data[list(data.keys())[0]], triples_map_element, predicate_object_map.object_map)
															else:
																if isinstance(data, list):
																	hash_maker(data, triples_map_element, predicate_object_map.object_map)
																elif len(data) < 2:
																	hash_maker(data[list(data.keys())[0]], triples_map_element, predicate_object_map.object_map)
												if child_list_value(predicate_object_map.object_map.child,row) in join_table[triples_map_element.triples_map_id + "_" + predicate_object_map.object_map.child[0]]:
													object_list = join_table[triples_map_element.triples_map_id + "_" + predicate_object_map.object_map.child[0]][row[predicate_object_map.object_map.child[0]]]
												else:
													object_list = []
												no_update = False
									object = None
								else:
									if (triples_map_element.triples_map_id + "_" + child_list(predicate_object_map.object_map.child)) not in join_table:
										if str(triples_map_element.file_format).lower() == "csv" or triples_map_element.file_format == "JSONPath":
											with open(str(triples_map_element.data_source), "r") as input_file_descriptor:
												if str(triples_map_element.file_format).lower() == "csv":
													data = csv.DictReader(input_file_descriptor, delimiter=delimiter)
													hash_maker_list(data, triples_map_element, predicate_object_map.object_map)
												else:
													data = json.load(input_file_descriptor)
													if isinstance(data, list):
														hash_maker_list(data, triples_map_element, predicate_object_map.object_map)
													elif len(data) < 2:
														hash_maker_list(data[list(data.keys())[0]], triples_map_element, predicate_object_map.object_map)

										elif triples_map_element.file_format == "XPath":
											with open(str(triples_map_element.data_source), "r") as input_file_descriptor:
												child_tree = ET.parse(input_file_descriptor)
												child_root = child_tree.getroot()
												hash_maker_xml(child_root, triples_map_element, predicate_object_map.object_map)						
										else:
											database, query_list = translate_sql(triples_map)
											db = connector.connect(host=host, port=int(port), user=user, password=password)
											cursor = db.cursor(buffered=True)
											cursor.execute("use " + database)
											for query in query_list:
												cursor.execute(query)
											hash_maker_array(cursor, triples_map_element, predicate_object_map.object_map)
									if sublist(predicate_object_map.object_map.child,row.keys()):
										if child_list_value(predicate_object_map.object_map.child,row) in join_table[triples_map_element.triples_map_id + "_" + child_list(predicate_object_map.object_map.child)]:
											object_list = join_table[triples_map_element.triples_map_id + "_" + child_list(predicate_object_map.object_map.child)][child_list_value(predicate_object_map.object_map.child,row)]
										else:
											object_list = []
									object = None
							else:
								if predicate_object_map.object_map.parent != None:
									if predicate_object_map.object_map.parent[0] != predicate_object_map.object_map.child[0]:
										if (triples_map_element.triples_map_id + "_" + child_list(predicate_object_map.object_map.child)) not in join_table:
											with open(str(triples_map_element.data_source), "r") as input_file_descriptor:
												if str(triples_map_element.file_format).lower() == "csv":
													parent_data = csv.DictReader(input_file_descriptor, delimiter=delimiter)
													hash_maker_list(parent_data, triples_map_element, predicate_object_map.object_map)
												else:
													parent_data = json.load(input_file_descriptor)
													if isinstance(parent_data, list):
														hash_maker_list(parent_data, triples_map_element, predicate_object_map.object_map)
													else:
														hash_maker_list(parent_data[list(parent_data.keys())[0]], triples_map_element, predicate_object_map.object_map)
										if sublist(predicate_object_map.object_map.child,row.keys()):
											if child_list_value(predicate_object_map.object_map.child,row) in join_table[triples_map_element.triples_map_id + "_" + child_list(predicate_object_map.object_map.child)]:
												object_list = join_table[triples_map_element.triples_map_id + "_" + child_list(predicate_object_map.object_map.child)][child_list_value(predicate_object_map.object_map.child,row)]
											else:
												object_list = []
										object = None
									else:
										try:
											object = "<" + string_substitution(triples_map_element.subject_map.value, "{(.+?)}", row, "object",ignore, triples_map.iterator) + ">"
										except TypeError:
											object = None
								else:
									try:
										object = "<" + string_substitution(triples_map_element.subject_map.value, "{(.+?)}", row, "object",ignore, triples_map.iterator) + ">"
									except TypeError:
										object = None
							break
						else:
							continue
				else:
					object = None
			else:
				object = None

			if duplicate == "yes":
				if predicate in general_predicates:
					dictionary_table_update(predicate + "_" + predicate_object_map.object_map.value)
				else:
					dictionary_table_update(predicate)					

			if predicate != None and object != None and subject != None:
				for graph in triples_map.subject_map.graph:
					triple = subject + " " + predicate + " " + object + ".\n"
					if graph != None and "defaultGraph" not in graph:
						if "{" in graph:
							triple = triple[:-2] + " <" + string_substitution(graph, "{(.+?)}", row, "subject",ignore, triples_map.iterator) + ">.\n"
							dictionary_table_update("<" + string_substitution(graph, "{(.+?)}", row, "subject",ignore, triples_map.iterator) + ">")
						else:
							triple = triple[:-2] + " <" + graph + ">.\n"
							dictionary_table_update("<" + graph + ">")

					if duplicate == "yes":
						dictionary_table_update(subject)
						dictionary_table_update(object)
						if predicate in general_predicates:
							if dic_table[predicate + "_" + predicate_object_map.object_map.value] not in g_triples:
								kg += triple
								g_triples.update({dic_table[predicate + "_" + predicate_object_map.object_map.value] : {dic_table[subject] + "_" + dic_table[object]: ""}})
							elif dic_table[subject] + "_" + dic_table[object] not in g_triples[dic_table[predicate + "_" + predicate_object_map.object_map.value]]:
								kg += triple
								g_triples[dic_table[predicate + "_" + predicate_object_map.object_map.value]].update({dic_table[subject] + "_" + dic_table[object]: ""})
						else:
							if dic_table[predicate] not in g_triples:					
								kg += triple
								g_triples.update({dic_table[predicate] : {dic_table[subject] + "_" + dic_table[object]: ""}})
							elif dic_table[subject] + "_" + dic_table[object] not in g_triples[dic_table[predicate]]:
								kg += triple
								g_triples[dic_table[predicate]].update({dic_table[subject] + "_" + dic_table[object]: ""})
					else:
						kg += triple
				if predicate[1:-1] in predicate_object_map.graph:
					triple = subject + " " + predicate + " " + object + ".\n"
					if predicate_object_map.graph[predicate[1:-1]] != None and "defaultGraph" not in predicate_object_map.graph[predicate[1:-1]]:
						if "{" in predicate_object_map.graph[predicate[1:-1]]:
							triple = triple[:-2] + " <" + string_substitution(predicate_object_map.graph[predicate[1:-1]], "{(.+?)}", row, "subject",ignore, triples_map.iterator) + ">.\n"
							dictionary_table_update("<" + string_substitution(predicate_object_map.graph[predicate[1:-1]], "{(.+?)}", row, "subject",ignore, triples_map.iterator) + ">")
						else:
							triple = triple[:-2] + " <" + predicate_object_map.graph[predicate[1:-1]] + ">.\n"
							dictionary_table_update("<" + predicate_object_map.graph[predicate[1:-1]] + ">")
						if duplicate == "yes":
							if predicate in general_predicates:
								if dic_table[predicate + "_" + predicate_object_map.object_map.value] not in g_triples:					
									kg += triple
									g_triples.update({dic_table[predicate + "_" + predicate_object_map.object_map.value] : {dic_table[subject] + "_" + dic_table[object]: ""}})
								elif dic_table[subject] + "_" + dic_table[object] not in g_triples[predicate + "_" + predicate_object_map.object_map.value]:
									kg += triple
									g_triples[dic_table[predicate + "_" + predicate_object_map.object_map.value]].update({dic_table[subject] + "_" + dic_table[object]: ""})
							else:
								if dic_table[predicate] not in g_triples:					
									kg += triple
									g_triples.update({dic_table[predicate] : {dic_table[subject] + "_" + dic_table[object]: ""}})
								elif dic_table[subject] + "_" + dic_table[object] not in g_triples[dic_table[predicate]]:
									kg += triple
									g_triples[dic_table[predicate]].update({dic_table[subject] + "_" + dic_table[object]: ""})
						else:
							kg += triple
			elif predicate != None and subject != None and object_list:
				for obj in object_list:
					if obj != None:
						for graph in triples_map.subject_map.graph:
							if predicate_object_map.object_map.term != None:
								if "IRI" in predicate_object_map.object_map.term:
									triple = subject + " " + predicate + " <" + obj[1:-1] + ">.\n"
								else:
									triple = subject + " " + predicate + " " + obj + ".\n"
							else:
								triple = subject + " " + predicate + " " + obj + ".\n"
							if graph != None and "defaultGraph" not in graph:
								if "{" in graph:
									triple = triple[:-2] + " <" + string_substitution(graph, "{(.+?)}", row, "subject",ignore, triples_map.iterator) + ">.\n"
									dictionary_table_update("<" + string_substitution(graph, "{(.+?)}", row, "subject",ignore, triples_map.iterator) + ">")
								else:
									triple = triple[:-2] + " <" + graph + ">.\n"
									dictionary_table_update("<" + graph + ">")
							if duplicate == "yes":
								dictionary_table_update(subject)
								dictionary_table_update(obj)	
								if predicate in general_predicates:
									if dic_table[predicate + "_" + predicate_object_map.object_map.value] not in g_triples:
										kg += triple
										g_triples.update({dic_table[predicate + "_" + predicate_object_map.object_map.value] : {dic_table[subject] + "_" + dic_table[obj]: ""}})
									elif dic_table[subject] + "_" + dic_table[obj] not in g_triples[dic_table[predicate + "_" + predicate_object_map.object_map.value]]:
										kg += triple
										g_triples[dic_table[predicate + "_" + predicate_object_map.object_map.value]].update({dic_table[subject] + "_" + dic_table[obj]: ""})
								else:
									if dic_table[predicate] not in g_triples:
										kg += triple
										g_triples.update({dic_table[predicate] : {dic_table[subject] + "_" + dic_table[obj]: ""}})
									elif dic_table[subject] + "_" + dic_table[obj] not in g_triples[dic_table[predicate]]:
										kg += triple
										g_triples[dic_table[predicate]].update({dic_table[subject] + "_" + dic_table[obj]: ""})

							else:
								kg += triple

						if predicate[1:-1] in predicate_object_map.graph:
							if predicate_object_map.object_map.term != None:
								if "IRI" in predicate_object_map.object_map.term:
									triple = subject + " " + predicate + " <" + obj[1:-1] + ">.\n"
								else:
									triple = subject + " " + predicate + " " + obj + ".\n"
							else:
								triple = subject + " " + predicate + " " + obj + ".\n"
							if predicate_object_map.graph[predicate[1:-1]] != None and "defaultGraph" not in predicate_object_map.graph[predicate[1:-1]]:
								if "{" in predicate_object_map.graph[predicate[1:-1]]:
									triple = triple[:-2] + " <" + string_substitution(predicate_object_map.graph[predicate[1:-1]], "{(.+?)}", row, "subject",ignore, triples_map.iterator) + ">.\n"
									dictionary_table_update("<" + string_substitution(predicate_object_map.graph[predicate[1:-1]], "{(.+?)}", row, "subject",ignore, triples_map.iterator) + ">")
								else:
									triple = triple[:-2] + " <" + predicate_object_map.graph[predicate[1:-1]] + ">.\n"
									dictionary_table_update("<" + predicate_object_map.graph[predicate[1:-1]] + ">")
								if duplicate == "yes":
									if predicate in general_predicates:
										if dic_table[predicate + "_" + predicate_object_map.object_map.value] not in g_triples:					
											kg += triple
											g_triples.update({dic_table[predicate + "_" + predicate_object_map.object_map.value] : {dic_table[subject] + "_" + dic_table[obj]: ""}})
										elif dic_table[subject] + "_" + dic_table[obj] not in g_triples[dic_table[predicate + "_" + predicate_object_map.object_map.value]]:
											kg += triple
											g_triples[dic_table[predicate + "_" + predicate_object_map.object_map.value]].update({dic_table[subject] + "_" + dic_table[obj]: ""})
									else:
										if dic_table[predicate] not in g_triples:					
											kg += triple
											g_triples.update({dic_table[predicate] : {dic_table[subject] + "_" + dic_table[obj]: ""}})
										elif dic_table[subject] + "_" + dic_table[obj] not in g_triples[dic_table[predicate]]:
											kg += triple
											g_triples[dic_table[predicate]].update({dic_table[subject] + "_" + dic_table[obj]: ""})
								else:
									kg += triple
				object_list = []
			else:
				continue
	return kg 

def semantify(remove_duplicate):
	start_time = time.time()
	kg = ""
	global duplicate
	duplicate = remove_duplicate
	print("Beginning Knowledge Graph Cration Process.")
	mapping = generate_mapping()
	triples_map_list = mapping_parser(mapping)
	sorted_sources, predicate_list, order_list = files_sort(triples_map_list, "no")
	with ThreadPoolExecutor(max_workers=10) as executor:
		for source in sorted_sources["csv"]:
			with open(source, "r", encoding = "utf-8") as input_file_descriptor:
				data = csv.DictReader(input_file_descriptor, delimiter=',')
				for triples_map in sorted_sources["csv"][source]:
					kg += executor.submit(semantify_file, sorted_sources["csv"][source][triples_map], triples_map_list, ",", data).result()
					if duplicate == "yes":
						predicate_list = release_PTT(sorted_sources["csv"][source][triples_map],predicate_list)
	"""from pyspark.sql import SparkSession
				sparkSession = SparkSession.builder.appName("example-pyspark-read-and-write").getOrCreate()
				data = {"Knowledge_Graph":kg}
				sparkSession.sparkContext.parallelize([data]).toDF().write.json("hdfs://localhost:8020/example")"""
	if not os.path.exists("./rdf-dump"):
		os.mkdir("./rdf-dump")
	with open("./rdf-dump/engiedata.nt", "w", encoding = "utf-8") as output_file_descriptor:
		output_file_descriptor.write(kg)
	os.system("docker run -it -v $(pwd)/rdf-dump:/data --rm --net hadoop_spark-net -e \"CORE_CONF_fs_defaultFS=hdfs://namenode:8020\" fmoghaddam/sansanamenode:v1 hdfs dfs -copyFromLocal -f /data /user/test")
	os.system("rm ./rdf-dump/engiedata.nt")
	os.system("rmdir ./rdf-dump/")
	kg = ""
	duration = time.time() - start_time
	print("Successfully semantified all datasets in {:.3f} seconds.".format(duration))
	print("The Process has ended.")
	return True
