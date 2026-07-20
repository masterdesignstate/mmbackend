import csv
import hashlib
import mimetypes
import os
import random
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from api.models import Question, User, UserAnswer, UserPicture, UserRequiredQuestion


DEFAULT_CSV = "/Users/dimi/Downloads/Notes_Dimi - Dummy.csv"
DEFAULT_MEN_DIR = "/Users/dimi/Downloads/dummy_dating_users_thispersonnotexist_split/men"
DEFAULT_WOMEN_DIR = "/Users/dimi/Downloads/dummy_dating_users_thispersonnotexist_split/women"
DUMMY_EMAIL_DOMAIN = "dummy.matchmatical.local"
EXPECTED_USER_COUNT = 1000
EXPECTED_GENDER_COUNT = 500
EXPECTED_MANDATORY_QUESTION_COUNT = 30
ALLOWED_PHOTO_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}

# This command intentionally uses a local first-name map so imports are deterministic
# and do not depend on a network service. It covers every distinct first name in the
# provided dummy CSV. The three overrides are unisex names selected to enforce the
# requested 500 male / 500 female import split.
FIRST_NAME_GENDERS = {
    'Aaron': 'male',
    'Abel': 'male',
    'Abigail': 'female',
    'Abraham': 'male',
    'Ada': 'female',
    'Adaline': 'female',
    'Adam': 'male',
    'Adan': 'male',
    'Aden': 'male',
    'Adrian': 'male',
    'Adriana': 'female',
    'Ahmad': 'male',
    'Ahmed': 'male',
    'Aidan': 'male',
    'Aiden': 'male',
    'Aileen': 'female',
    'Ainsley': 'female',
    'Alan': 'male',
    'Alana': 'female',
    'Alba': 'female',
    'Albert': 'male',
    'Aleah': 'female',
    'Alec': 'male',
    'Alejandra': 'female',
    'Alejandro': 'male',
    'Alex': 'male',
    'Alexa': 'female',
    'Alexander': 'male',
    'Alexandra': 'female',
    'Alexis': 'female',
    'Alfonso': 'male',
    'Alfred': 'male',
    'Alfredo': 'male',
    'Ali': 'male',
    'Alice': 'female',
    'Alicia': 'female',
    'Alina': 'female',
    'Alison': 'female',
    'Aliza': 'female',
    'Allen': 'male',
    'Allie': 'female',
    'Alondra': 'female',
    'Alonzo': 'male',
    'Alvaro': 'male',
    'Alyssa': 'female',
    'Amanda': 'female',
    'Amara': 'female',
    'Amari': 'male',
    'Amaya': 'female',
    'Amber': 'female',
    'Ambrose': 'male',
    'Amelia': 'female',
    'Amina': 'female',
    'Amir': 'male',
    'Amy': 'female',
    'Anastasia': 'female',
    'Anderson': 'male',
    'Andre': 'male',
    'Andrea': 'female',
    'Andres': 'male',
    'Andrew': 'male',
    'Andy': 'male',
    'Angel': 'male',
    'Angela': 'female',
    'Angelica': 'female',
    'Angelina': 'female',
    'Angelo': 'male',
    'Anika': 'female',
    'Anita': 'female',
    'Ann': 'female',
    'Anna': 'female',
    'Annabelle': 'female',
    'Anne': 'female',
    'Annie': 'female',
    'Anthony': 'male',
    'Anton': 'male',
    'Antonio': 'male',
    'Apollo': 'male',
    'April': 'female',
    'Archer': 'male',
    'Archie': 'male',
    'Ari': 'male',
    'Aria': 'female',
    'Ariana': 'female',
    'Arianna': 'female',
    'Ariel': 'female',
    'Ariella': 'female',
    'Arlo': 'male',
    'Armando': 'male',
    'Armani': 'male',
    'Aron': 'male',
    'Arthur': 'male',
    'Arturo': 'male',
    'Arya': 'female',
    'Asa': 'male',
    'Asher': 'male',
    'Ashley': 'female',
    'Ashlyn': 'female',
    'Ashton': 'male',
    'Aspen': 'female',
    'Athena': 'female',
    'Atticus': 'male',
    'Aubree': 'female',
    'Aubrey': 'female',
    'Audrey': 'female',
    'August': 'male',
    'Augustine': 'male',
    'Augustus': 'male',
    'Aurora': 'female',
    'Austen': 'male',
    'Austin': 'male',
    'Autumn': 'female',
    'Ava': 'female',
    'Avery': 'female',
    'Axel': 'male',
    'Axton': 'male',
    'Azalea': 'female',
    'Aziel': 'male',
    'Bailey': 'female',
    'Barbara': 'female',
    'Barrett': 'male',
    'Beatrice': 'female',
    'Beatrix': 'female',
    'Beau': 'male',
    'Beckett': 'male',
    'Belinda': 'female',
    'Bella': 'female',
    'Belle': 'female',
    'Benjamin': 'male',
    'Bennett': 'male',
    'Benny': 'male',
    'Benson': 'male',
    'Bentley': 'male',
    'Bernard': 'male',
    'Beth': 'female',
    'Bethany': 'female',
    'Bianca': 'female',
    'Billy': 'male',
    'Blaine': 'male',
    'Blair': 'female',
    'Blake': 'male',
    'Bo': 'male',
    'Bobby': 'male',
    'Bodhi': 'male',
    'Bonnie': 'female',
    'Boris': 'male',
    'Boston': 'male',
    'Bowen': 'male',
    'Bradley': 'male',
    'Brady': 'male',
    'Branden': 'male',
    'Brandi': 'female',
    'Brandon': 'male',
    'Brandy': 'female',
    'Brantley': 'male',
    'Braxton': 'male',
    'Brayden': 'male',
    'Brenda': 'female',
    'Brendan': 'male',
    'Brenden': 'male',
    'Brent': 'male',
    'Brenton': 'male',
    'Bret': 'male',
    'Brett': 'male',
    'Brian': 'male',
    'Briana': 'female',
    'Brianna': 'female',
    'Briar': 'male',
    'Brice': 'male',
    'Bridget': 'female',
    'Brittany': 'female',
    'Brock': 'male',
    'Broderick': 'male',
    'Brody': 'male',
    'Brogan': 'male',
    'Bronson': 'male',
    'Brooke': 'female',
    'Brooklyn': 'female',
    'Brooks': 'male',
    'Bruce': 'male',
    'Bruno': 'male',
    'Bryan': 'male',
    'Bryant': 'male',
    'Bryce': 'male',
    'Bryson': 'male',
    'Byron': 'male',
    'Cade': 'male',
    'Caden': 'male',
    'Cadence': 'female',
    'Cael': 'male',
    'Caiden': 'male',
    'Cain': 'male',
    'Caitlin': 'female',
    'Caitlyn': 'female',
    'Caleb': 'male',
    'Callan': 'male',
    'Callum': 'male',
    'Calvin': 'male',
    'Camden': 'male',
    'Cameron': 'male',
    'Camila': 'female',
    'Camille': 'female',
    'Canaan': 'male',
    'Candace': 'female',
    'Cannon': 'male',
    'Cara': 'female',
    'Carina': 'female',
    'Carl': 'male',
    'Carla': 'female',
    'Carlo': 'male',
    'Carlos': 'male',
    'Carlton': 'male',
    'Carmen': 'female',
    'Carolina': 'female',
    'Caroline': 'female',
    'Carolyn': 'female',
    'Carson': 'male',
    'Carter': 'male',
    'Casey': 'male',
    'Cash': 'male',
    'Caspian': 'male',
    'Cassandra': 'female',
    'Cassidy': 'female',
    'Cassie': 'female',
    'Cassius': 'male',
    'Catherine': 'female',
    'Cayden': 'male',
    'Cecelia': 'female',
    'Cecilia': 'female',
    'Cedric': 'male',
    'Celeste': 'female',
    'Celia': 'female',
    'Cesar': 'male',
    'Chad': 'male',
    'Chandler': 'male',
    'Chanel': 'female',
    'Charlene': 'female',
    'Charles': 'male',
    'Charlie': 'male',
    'Charlotte': 'female',
    'Chase': 'male',
    'Chelsea': 'female',
    'Cherish': 'female',
    'Cheryl': 'female',
    'Cheyenne': 'female',
    'Chloe': 'female',
    'Chris': 'male',
    'Christian': 'male',
    'Christina': 'female',
    'Christine': 'female',
    'Christopher': 'male',
    'Ciara': 'female',
    'Cindy': 'female',
    'Claire': 'female',
    'Clara': 'female',
    'Clarissa': 'female',
    'Clark': 'male',
    'Claudia': 'female',
    'Clay': 'male',
    'Clayton': 'male',
    'Clyde': 'male',
    'Cohen': 'male',
    'Colby': 'male',
    'Cole': 'male',
    'Colette': 'female',
    'Colin': 'male',
    'Collin': 'male',
    'Colt': 'male',
    'Colten': 'male',
    'Colton': 'male',
    'Conner': 'male',
    'Connie': 'female',
    'Connor': 'male',
    'Conrad': 'male',
    'Cooper': 'male',
    'Cora': 'female',
    'Coral': 'female',
    'Corbin': 'male',
    'Cordelia': 'female',
    'Corey': 'male',
    'Corinne': 'female',
    'Cortez': 'male',
    'Cory': 'male',
    'Courtney': 'female',
    'Craig': 'male',
    'Cristian': 'male',
    'Cruz': 'male',
    'Crystal': 'female',
    'Cullen': 'male',
    'Curtis': 'male',
    'Cynthia': 'female',
    'Cyrus': 'male',
    'Dahlia': 'female',
    'Daisy': 'female',
    'Dakota': 'male',
    'Dale': 'male',
    'Dallas': 'male',
    'Dalton': 'male',
    'Damian': 'male',
    'Damien': 'male',
    'Damon': 'male',
    'Dana': 'female',
    'Dane': 'male',
    'Daniel': 'male',
    'Daniela': 'female',
    'Daniella': 'female',
    'Danielle': 'female',
    'Danny': 'male',
    'Dante': 'male',
    'Daphne': 'female',
    'Darian': 'male',
    'Darius': 'male',
    'Darlene': 'female',
    'Darrell': 'male',
    'Darren': 'male',
    'Darryl': 'male',
    'Daryl': 'male',
    'Dash': 'male',
    'David': 'male',
    'Davina': 'female',
    'Davis': 'male',
    'Dawson': 'male',
    'Dax': 'male',
    'Daxton': 'male',
    'Dayton': 'male',
    'Deacon': 'male',
    'Dean': 'male',
    'Deborah': 'female',
    'Declan': 'male',
    'Delaney': 'female',
    'Delilah': 'female',
    'Demetrius': 'male',
    'Demi': 'female',
    'Denise': 'female',
    'Dennis': 'male',
    'Derek': 'male',
    'Derrick': 'male',
    'Desiree': 'female',
    'Desmond': 'male',
    'Destiny': 'female',
    'Devin': 'male',
    'Devon': 'male',
    'Dexter': 'male',
    'Diana': 'female',
    'Diane': 'female',
    'Diego': 'male',
    'Dillon': 'male',
    'Dina': 'female',
    'Dolores': 'female',
    'Dominic': 'male',
    'Dominick': 'male',
    'Dominique': 'female',
    'Donald': 'male',
    'Donna': 'female',
    'Donovan': 'male',
    'Dorian': 'male',
    'Dorothy': 'female',
    'Douglas': 'male',
    'Drake': 'male',
    'Drew': 'male',
    'Duke': 'male',
    'Duncan': 'male',
    'Dustin': 'male',
    'Dwayne': 'male',
    'Dwight': 'male',
    'Dylan': 'male',
    'Ean': 'male',
    'Easton': 'male',
    'Eddie': 'male',
    'Eden': 'female',
    'Edgar': 'male',
    'Edison': 'male',
    'Edith': 'female',
    'Edmund': 'male',
    'Edward': 'male',
    'Edwin': 'male',
    'Eileen': 'female',
    'Elaine': 'female',
    'Eleanor': 'female',
    'Elena': 'female',
    'Eliana': 'female',
    'Elias': 'male',
    'Elijah': 'male',
    'Elio': 'male',
    'Elisa': 'female',
    'Elisabeth': 'female',
    'Elise': 'female',
    'Eliza': 'female',
    'Elizabeth': 'female',
    'Ella': 'female',
    'Ellen': 'female',
    'Elliana': 'female',
    'Ellie': 'female',
    'Elliot': 'male',
    'Elliott': 'male',
    'Ellis': 'male',
    'Elmer': 'male',
    'Eloise': 'female',
    'Elsa': 'female',
    'Elsie': 'female',
    'Elton': 'male',
    'Elvin': 'male',
    'Elvira': 'female',
    'Elvis': 'male',
    'Ember': 'female',
    'Emely': 'female',
    'Emerson': 'male',
    'Emery': 'female',
    'Emilia': 'female',
    'Emiliano': 'male',
    'Emilio': 'male',
    'Emily': 'female',
    'Emma': 'female',
    'Emmanuel': 'male',
    'Emmett': 'male',
    'Emory': 'male',
    'Enoch': 'male',
    'Enrique': 'male',
    'Enzo': 'male',
    'Ephraim': 'male',
    'Eric': 'male',
    'Erica': 'female',
    'Erick': 'male',
    'Erik': 'male',
    'Erika': 'female',
    'Erin': 'female',
    'Ernest': 'male',
    'Ernesto': 'male',
    'Esme': 'female',
    'Esmeralda': 'female',
    'Esteban': 'male',
    'Estelle': 'female',
    'Esther': 'female',
    'Ethan': 'male',
    'Etta': 'female',
    'Eugene': 'male',
    'Eugenia': 'female',
    'Eunice': 'female',
    'Eva': 'female',
    'Evan': 'male',
    'Evangeline': 'female',
    'Eve': 'female',
    'Evelyn': 'female',
    'Everett': 'male',
    'Everly': 'female',
    'Ezekiel': 'male',
    'Ezra': 'male',
    'Fabian': 'male',
    'Faith': 'female',
    'Fallon': 'female',
    'Farah': 'female',
    'Fatima': 'female',
    'Fawn': 'female',
    'Faye': 'female',
    'Felicia': 'female',
    'Felipe': 'male',
    'Felix': 'male',
    'Fernanda': 'female',
    'Fernando': 'male',
    'Finley': 'female',
    'Finn': 'male',
    'Finnegan': 'male',
    'Fiona': 'female',
    'Fletcher': 'male',
    'Florence': 'female',
    'Floyd': 'male',
    'Flynn': 'male',
    'Ford': 'male',
    'Forrest': 'male',
    'Foster': 'male',
    'Frances': 'female',
    'Francesca': 'female',
    'Francis': 'male',
    'Francisco': 'male',
    'Frank': 'male',
    'Frankie': 'male',
    'Franklin': 'male',
    'Frederick': 'male',
    'Freya': 'female',
    'Gabriel': 'male',
    'Gabriela': 'female',
    'Gabriella': 'female',
    'Gabrielle': 'female',
    'Gael': 'male',
    'Gage': 'male',
    'Galilea': 'female',
    'Garrett': 'male',
    'Garrison': 'male',
    'Gary': 'male',
    'Gavin': 'male',
    'Gemma': 'female',
    'Genesis': 'female',
    'Geneva': 'female',
    'Genevieve': 'female',
    'George': 'male',
    'Georgia': 'female',
    'Georgina': 'female',
    'Gerald': 'male',
    'Geraldine': 'female',
    'Gerard': 'male',
    'Giana': 'female',
    'Gideon': 'male',
    'Gigi': 'female',
    'Gilbert': 'male',
    'Gillian': 'female',
    'Gina': 'female',
    'Gino': 'male',
    'Giovanna': 'female',
    'Giovanni': 'male',
    'Giselle': 'female',
    'Glen': 'male',
    'Glenda': 'female',
    'Glenn': 'male',
    'Gloria': 'female',
    'Gordon': 'male',
    'Grady': 'male',
    'Graham': 'male',
    'Grant': 'male',
    'Grayson': 'male',
    'Gregory': 'male',
    'Gretchen': 'female',
    'Griffin': 'male',
    'Guadalupe': 'female',
    'Gunnar': 'male',
    'Gunner': 'male',
    'Gustavo': 'male',
    'Guy': 'male',
    'Gwen': 'female',
    'Gwendolyn': 'female',
    'Hadley': 'female',
    'Hailey': 'female',
    'Haleigh': 'female',
    'Haley': 'female',
    'Hank': 'male',
    'Hannah': 'female',
    'Harley': 'male',
    'Harmony': 'female',
    'Harold': 'male',
    'Harper': 'female',
    'Harrison': 'male',
    'Harvey': 'male',
    'Hassan': 'male',
    'Hayden': 'male',
    'Hazel': 'female',
    'Heath': 'male',
    'Heather': 'female',
    'Hector': 'male',
    'Heidi': 'female',
    'Helen': 'female',
    'Helena': 'female',
    'Henry': 'male',
    'Herbert': 'male',
    'Herman': 'male',
    'Holden': 'male',
    'Holly': 'female',
    'Hope': 'female',
    'Houston': 'male',
    'Howard': 'male',
    'Hudson': 'male',
    'Hugh': 'male',
    'Hugo': 'male',
    'Hunter': 'male',
    'Ian': 'male',
    'Ibrahim': 'male',
    'Ignacio': 'male',
    'Iliana': 'female',
    'Imani': 'female',
    'Imogen': 'female',
    'Imran': 'male',
    'India': 'female',
    'Indie': 'female',
    'Inez': 'female',
    'Ingrid': 'female',
    'Ira': 'male',
    'Irene': 'female',
    'Iris': 'female',
    'Isaac': 'male',
    'Isabel': 'female',
    'Isabela': 'female',
    'Isabelle': 'female',
    'Isaiah': 'male',
    'Isaias': 'male',
    'Ishmael': 'male',
    'Isiah': 'male',
    'Isis': 'female',
    'Ismael': 'male',
    'Israel': 'male',
    'Ivan': 'male',
    'Ivanna': 'female',
    'Ivory': 'female',
    'Ivy': 'female',
    'Izabella': 'female',
    'Izaiah': 'male',
    'Jace': 'male',
    'Jack': 'male',
    'Jackson': 'male',
    'Jacob': 'male',
    'Jacqueline': 'female',
    'Jada': 'female',
    'Jade': 'female',
    'Jaden': 'male',
    'Jaelyn': 'female',
    'Jagger': 'male',
    'Jaime': 'male',
    'Jake': 'male',
    'Jakob': 'male',
    'Jalen': 'male',
    'Jamal': 'male',
    'James': 'male',
    'Jameson': 'male',
    'Jamie': 'female',
    'Jane': 'female',
    'Janelle': 'female',
    'Janessa': 'female',
    'Janet': 'female',
    'Janice': 'female',
    'Jared': 'male',
    'Jase': 'male',
    'Jasmine': 'female',
    'Jason': 'male',
    'Jasper': 'male',
    'Javier': 'male',
    'Jax': 'male',
    'Jaxon': 'male',
    'Jaxson': 'male',
    'Jay': 'male',
    'Jayce': 'male',
    'Jayden': 'male',
    'Jayla': 'female',
    'Jaylen': 'male',
    'Jayson': 'male',
    'Jean': 'female',
    'Jeanette': 'female',
    'Jeanne': 'female',
    'Jeannine': 'female',
    'Jefferson': 'male',
    'Jeffery': 'male',
    'Jeffrey': 'male',
    'Jenna': 'female',
    'Jennifer': 'female',
    'Jensen': 'male',
    'Jeremiah': 'male',
    'Jeremy': 'male',
    'Jericho': 'male',
    'Jermaine': 'male',
    'Jerome': 'male',
    'Jerry': 'male',
    'Jesse': 'male',
    'Jessica': 'female',
    'Jessie': 'male',
    'Jesus': 'male',
    'Jett': 'male',
    'Jewel': 'female',
    'Jillian': 'female',
    'Jim': 'male',
    'Jimmie': 'male',
    'Jimmy': 'male',
    'Joan': 'female',
    'Joanna': 'female',
    'Joanne': 'female',
    'Joaquin': 'male',
    'Jocelyn': 'female',
    'Jodi': 'female',
    'Jodie': 'female',
    'Joe': 'male',
    'Joel': 'male',
    'Joey': 'male',
    'John': 'male',
    'Johnathan': 'male',
    'Johnny': 'male',
    'Jon': 'male',
    'Jonah': 'male',
    'Jonas': 'male',
    'Jonathan': 'male',
    'Jordan': 'male',
    'Jorge': 'male',
    'Jose': 'male',
    'Joseph': 'male',
    'Josephine': 'female',
    'Josh': 'male',
    'Joshua': 'male',
    'Josiah': 'male',
    'Josue': 'male',
    'Jovan': 'male',
    'Joy': 'female',
    'Joyce': 'female',
    'Juan': 'male',
    'Judah': 'male',
    'Jude': 'male',
    'Judith': 'female',
    'Judy': 'female',
    'Julia': 'female',
    'Julian': 'male',
    'Juliana': 'female',
    'Julianna': 'female',
    'Julianne': 'female',
    'Julie': 'female',
    'Julien': 'male',
    'Juliet': 'female',
    'Juliette': 'female',
    'Julio': 'male',
    'Julius': 'male',
    'June': 'female',
    'Justice': 'male',
    'Justin': 'male',
    'Justina': 'female',
    'Kade': 'male',
    'Kaden': 'male',
    'Kai': 'male',
    'Kaiden': 'male',
    'Kaitlyn': 'female',
    'Kaleb': 'male',
    'Kameron': 'male',
    'Kane': 'male',
    'Kara': 'female',
    'Kareem': 'male',
    'Karen': 'female',
    'Kari': 'female',
    'Karina': 'female',
    'Karla': 'female',
    'Karson': 'male',
    'Karter': 'male',
    'Kassandra': 'female',
    'Katelyn': 'female',
    'Katherine': 'female',
    'Kathleen': 'female',
    'Kathryn': 'female',
    'Katie': 'female',
    'Kay': 'female',
    'Kayden': 'male',
    'Kayla': 'female',
    'Kaylee': 'female',
    'Keaton': 'male',
    'Keegan': 'male',
    'Keira': 'female',
    'Keith': 'male',
    'Kelly': 'female',
    'Kelsey': 'female',
    'Kelvin': 'male',
    'Ken': 'male',
    'Kendall': 'female',
    'Kendra': 'female',
    'Kendrick': 'male',
    'Kennedy': 'female',
    'Kenneth': 'male',
    'Kenny': 'male',
    'Kent': 'male',
    'Kenzie': 'female',
    'Kerry': 'male',
    'Kevin': 'male',
    'Khalil': 'male',
    'Kian': 'male',
    'Kieran': 'male',
    'Killian': 'male',
    'Kimberly': 'female',
    'King': 'male',
    'Kingsley': 'male',
    'Kingston': 'male',
    'Kinsley': 'female',
    'Kira': 'female',
    'Kirk': 'male',
    'Knox': 'male',
    'Kobe': 'male',
    'Kody': 'male',
    'Kolton': 'male',
    'Konnor': 'male',
    'Krista': 'female',
    'Kristen': 'female',
    'Kristina': 'female',
    'Kristy': 'female',
    'Kurt': 'male',
    'Kyla': 'female',
    'Kylan': 'male',
    'Kyle': 'male',
    'Kyler': 'male',
    'Kylie': 'female',
    'Kylo': 'male',
    'Kyree': 'male',
    'Lacey': 'female',
    'Laila': 'female',
    'Lance': 'male',
    'Landen': 'male',
    'Landon': 'male',
    'Lane': 'male',
    'Larry': 'male',
    'Laura': 'female',
    'Lauren': 'female',
    'Laurie': 'female',
    'Lawrence': 'male',
    'Lawson': 'male',
    'Layla': 'female',
    'Layton': 'male',
    'Lea': 'female',
    'Leah': 'female',
    'Leandro': 'male',
    'Leanna': 'female',
    'Ledger': 'male',
    'Lee': 'male',
    'Leila': 'female',
    'Leilani': 'female',
    'Lena': 'female',
    'Leo': 'male',
    'Leon': 'male',
    'Leonard': 'male',
    'Leonardo': 'male',
    'Leonel': 'male',
    'Leopold': 'male',
    'Leroy': 'male',
    'Lesley': 'female',
    'Leslie': 'female',
    'Leticia': 'female',
    'Levi': 'male',
    'Lewis': 'male',
    'Lia': 'female',
    'Liam': 'male',
    'Liana': 'female',
    'Libby': 'female',
    'Lila': 'female',
    'Lilian': 'female',
    'Liliana': 'female',
    'Lillian': 'female',
    'Lillie': 'female',
    'Lilly': 'female',
    'Lily': 'female',
    'Lincoln': 'male',
    'Linda': 'female',
    'Lindsay': 'female',
    'Lindsey': 'female',
    'Lionel': 'male',
    'Lisa': 'female',
    'Lisette': 'female',
    'Livia': 'female',
    'Liz': 'female',
    'Liza': 'female',
    'Lizbeth': 'female',
    'Lizette': 'female',
    'Logan': 'male',
    'Lola': 'female',
    'London': 'female',
    'Lorelai': 'female',
    'Lorelei': 'female',
    'Lorena': 'female',
    'Lorenzo': 'male',
    'Lori': 'female',
    'Lorraine': 'female',
    'Louis': 'male',
    'Louisa': 'female',
    'Luca': 'male',
    'Lucas': 'male',
    'Lucia': 'female',
    'Luciana': 'female',
    'Luciano': 'male',
    'Lucille': 'female',
    'Lucy': 'female',
    'Luis': 'male',
    'Luka': 'male',
    'Lukas': 'male',
    'Luke': 'male',
    'Luna': 'female',
    'Luther': 'male',
    'Lydia': 'female',
    'Lyla': 'female',
    'Lynette': 'female',
    'Lynn': 'female',
    'Lyric': 'female',
    'Mabel': 'female',
    'Mackenzie': 'female',
    'Macy': 'female',
    'Madalyn': 'female',
    'Maddison': 'female',
    'Maddox': 'male',
    'Madeleine': 'female',
    'Madeline': 'female',
    'Madelyn': 'female',
    'Madison': 'female',
    'Mae': 'female',
    'Maeve': 'female',
    'Magdalena': 'female',
    'Maggie': 'female',
    'Maia': 'female',
    'Maisie': 'female',
    'Makayla': 'female',
    'Makenna': 'female',
    'Malachi': 'male',
    'Malakai': 'male',
    'Malcolm': 'male',
    'Mallory': 'female',
    'Mandy': 'female',
    'Manuel': 'male',
    'Marc': 'male',
    'Marcel': 'male',
    'Marcie': 'female',
    'Marco': 'male',
    'Marcus': 'male',
    'Margaret': 'female',
    'Margot': 'female',
    'Maria': 'female',
    'Mariah': 'female',
    'Mariam': 'female',
    'Mariana': 'female',
    'Maribel': 'female',
    'Marie': 'female',
    'Marilyn': 'female',
    'Marina': 'female',
    'Mario': 'male',
    'Marisa': 'female',
    'Marisol': 'female',
    'Marissa': 'female',
    'Martha': 'female',
    'Mary': 'female',
    'Maryann': 'female',
    'Matilda': 'female',
    'Maura': 'female',
    'Maya': 'female',
    'Mckenzie': 'female',
    'Meadow': 'female',
    'Megan': 'female',
    'Melanie': 'female',
    'Melinda': 'female',
    'Melissa': 'female',
    'Melody': 'female',
    'Mercedes': 'female',
    'Meredith': 'female',
    'Mia': 'female',
    'Michaela': 'female',
    'Michelle': 'female',
    'Mikaela': 'female',
    'Mila': 'female',
    'Miley': 'female',
    'Mindy': 'female',
    'Miranda': 'female',
    'Miriam': 'female',
    'Misty': 'female',
    'Molly': 'female',
    'Monica': 'female',
    'Monique': 'female',
    'Morgan': 'female',
    'Myra': 'female',
    'Myriam': 'female',
    'Nadia': 'female',
    'Nancy': 'female',
    'Naomi': 'female',
    'Natalia': 'female',
    'Natalie': 'female',
    'Natasha': 'female',
    'Naya': 'female',
    'Nevaeh': 'female',
    'Nia': 'female',
    'Nicole': 'female',
    'Nina': 'female',
    'Noelle': 'female',
    'Nora': 'female',
    'Norma': 'female',
    'Nova': 'female',
    'Nyla': 'female',
    'Odessa': 'female',
    'Olga': 'female',
    'Olive': 'female',
    'Olivia': 'female',
    'Opal': 'female',
    'Paige': 'female',
    'Paloma': 'female',
    'Pamela': 'female',
    'Paris': 'female',
    'Patricia': 'female',
    'Paula': 'female',
    'Paulina': 'female',
    'Payton': 'female',
    'Penelope': 'female',
    'Perla': 'female',
    'Phoebe': 'female',
    'Piper': 'female',
    'Polly': 'female',
    'Priscilla': 'female',
    'Quinn': 'male',
    'Rachel': 'female',
    'Raelynn': 'female',
    'Ramona': 'female',
    'Raven': 'female',
    'Reagan': 'female',
    'Rebecca': 'female',
    'Reese': 'female',
    'Regina': 'female',
    'Renee': 'female',
    'Riley': 'female',
    'Rita': 'female'
}
GENDER_OVERRIDES = {"Blair": "female", "Emery": "female", "Riley": "female"}

FALLBACK_FROM_LOCATIONS = [
    "Austin, TX", "Dallas, TX", "Houston, TX", "San Antonio, TX",
    "California", "New York", "Florida", "Colorado", "Illinois",
    "Georgia", "Arizona", "Washington", "Oregon", "North Carolina",
    "Tennessee", "Massachusetts", "New Jersey", "Virginia",
]


@dataclass(frozen=True)
class ImportRow:
    row_number: int
    photo_index: int
    first_name: str
    last_name: str
    username: str
    tagline: str
    date_of_birth: date
    live: str
    bio: str
    answers: dict
    gender: str
    height: int
    from_location: str
    photo_path: Path | None = None
    photo_url: str | None = None


@dataclass(frozen=True)
class PlannedAnswer:
    question: Question
    me_answer: int
    me_open_to_all: bool
    looking_for_answer: int
    looking_for_open_to_all: bool


class AzureUploader:
    def __init__(self, blob_service_client, container_name, sas_token=""):
        self.blob_service_client = blob_service_client
        self.container_name = container_name
        self.sas_token = (sas_token or "").lstrip("?")

    @classmethod
    def from_environment(cls):
        connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        account_name = os.getenv("AZURE_ACCOUNT_NAME", getattr(settings, "AZURE_ACCOUNT_NAME", ""))
        account_key = os.getenv("AZURE_ACCOUNT_KEY", getattr(settings, "AZURE_ACCOUNT_KEY", ""))
        container_name = (
            os.getenv("AZURE_CONTAINER")
            or os.getenv("NEXT_PUBLIC_CONTAINER")
            or getattr(settings, "AZURE_CONTAINER", "")
            or "photos"
        )
        sas_token = (
            os.getenv("AZURE_STORAGE_SAS_TOKEN")
            or os.getenv("AZURE_SAS_TOKEN")
            or os.getenv("NEXT_PUBLIC_SAS_TOKEN")
            or ""
        )

        try:
            from azure.storage.blob import BlobServiceClient
        except ImportError as exc:
            raise CommandError("azure-storage-blob is not installed") from exc

        if connection_string:
            client = BlobServiceClient.from_connection_string(connection_string)
            return cls(client, container_name, sas_token)

        if not account_name or not account_key:
            raise CommandError(
                "Azure credentials are missing. Set AZURE_STORAGE_CONNECTION_STRING or "
                "AZURE_ACCOUNT_NAME/AZURE_ACCOUNT_KEY."
            )

        account_url = f"https://{account_name}.blob.core.windows.net"
        client = BlobServiceClient(account_url=account_url, credential=account_key)
        return cls(client, container_name, sas_token)

    def validate(self):
        if not self.container_name:
            raise CommandError("Azure container is missing. Set AZURE_CONTAINER.")
        self.blob_service_client.get_container_client(self.container_name)

    def upload(self, file_path: Path, blob_name: str) -> str:
        from azure.storage.blob import ContentSettings

        content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        container_client = self.blob_service_client.get_container_client(self.container_name)
        blob_client = container_client.get_blob_client(blob_name)
        with file_path.open("rb") as photo_file:
            blob_client.upload_blob(
                photo_file,
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type),
            )
        if self.sas_token and "?" not in blob_client.url:
            return f"{blob_client.url}?{self.sas_token}"
        return blob_client.url


def stable_int(*parts):
    digest = hashlib.sha256(":".join(str(part) for part in parts).encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def parse_int(raw, label, row_number):
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError) as exc:
        raise CommandError(f"Row {row_number} has invalid integer for {label}: {raw!r}") from exc


def parse_dob(raw, row_number):
    value = str(raw).strip()
    for fmt in ("%m/%d/%y", "%m/%d/%Y"):
        try:
            parsed = datetime.strptime(value, fmt).date()
            if parsed > date.today():
                parsed = parsed.replace(year=parsed.year - 100)
            return parsed
        except ValueError:
            pass
    raise CommandError(f"Row {row_number} has invalid DOB: {raw!r}")


def calculate_age(dob, today=None):
    today = today or date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def get_csv_headers(header_row):
    return {name.strip(): index for index, name in enumerate(header_row) if name.strip()}


def get_required_columns():
    base = ["First", "Last", "Username", "Tag Line", "DOB", "Live", "Bio"]
    answer_cols = ["1b"] + [f"{number}{suffix}" for number in range(2, 11) for suffix in ("a", "b")]
    return base + answer_cols


def read_dummy_csv(csv_path):
    path = Path(csv_path)
    if not path.exists():
        raise CommandError(f"CSV not found: {path}")

    with path.open(newline="", encoding="utf-8-sig") as csv_file:
        rows = list(csv.reader(csv_file))

    if len(rows) < 4:
        raise CommandError("CSV must include two pre-header rows, one header row, and data rows")

    headers = get_csv_headers(rows[2])
    missing = [column for column in get_required_columns() if column not in headers]
    if missing:
        raise CommandError(f"CSV is missing required columns: {', '.join(missing)}")

    parsed_rows = []
    for offset, row in enumerate(rows[3:], start=4):
        if not any(cell.strip() for cell in row):
            continue

        def cell(column):
            index = headers[column]
            return row[index].strip() if index < len(row) else ""

        first_name = cell("First")
        gender = FIRST_NAME_GENDERS.get(first_name)
        if not gender:
            gender = None

        answers = {"1b": parse_int(cell("1b"), "1b", offset)}
        for number in range(2, 11):
            for suffix in ("a", "b"):
                column = f"{number}{suffix}"
                answers[column] = parse_int(cell(column), column, offset)

        parsed_rows.append({
            "row_number": offset,
            "photo_index": parse_int(row[1].strip(), "Photos index", offset) if len(row) > 1 and row[1].strip() else len(parsed_rows) + 1,
            "first_name": first_name,
            "last_name": cell("Last"),
            "username": cell("Username"),
            "tagline": cell("Tag Line"),
            "date_of_birth": parse_dob(cell("DOB"), offset),
            "live": cell("Live"),
            "bio": cell("Bio"),
            "answers": answers,
            "gender": gender,
        })

    return parsed_rows


def resolve_genders(raw_rows):
    unresolved = sorted({row["first_name"] for row in raw_rows if not row.get("gender")})
    if unresolved:
        raise CommandError("Unmapped first names: " + ", ".join(unresolved))

    counts = {"male": 0, "female": 0}
    for row in raw_rows:
        counts[row["gender"]] += 1

    if counts["male"] != EXPECTED_GENDER_COUNT or counts["female"] != EXPECTED_GENDER_COUNT:
        raise CommandError(
            f"Gender inference must produce {EXPECTED_GENDER_COUNT} men and {EXPECTED_GENDER_COUNT} women; "
            f"got {counts['male']} men and {counts['female']} women."
        )
    return counts


def list_usable_photos(directory):
    path = Path(directory)
    if not path.exists() or not path.is_dir():
        raise CommandError(f"Photo directory not found: {path}")
    return sorted(
        child for child in path.iterdir()
        if child.is_file() and child.suffix.lower() in ALLOWED_PHOTO_SUFFIXES and child.stat().st_size > 0
    )


def assign_unique_usernames(raw_rows):
    usernames = [row["username"] for row in raw_rows]
    blank = [row["row_number"] for row in raw_rows if not row["username"]]
    if blank:
        raise CommandError(f"Rows with blank username: {blank[:20]}")

    existing = set(User.objects.filter(username__in=usernames).values_list("username", flat=True))
    used = set(existing)
    adjusted = 0

    for row in raw_rows:
        base = row["username"]
        candidate = base
        suffix = 2
        while candidate in used:
            candidate = f"{base}_{suffix}"
            suffix += 1
        if candidate != base:
            adjusted += 1
            row["source_username"] = base
            row["username"] = candidate
        used.add(candidate)

    remaining_conflicts = set(User.objects.filter(username__in=[row["username"] for row in raw_rows]).values_list("username", flat=True))
    if remaining_conflicts:
        raise CommandError("Usernames already exist in database after suffixing: " + ", ".join(sorted(remaining_conflicts)[:20]))

    return adjusted


def get_from_locations(seed):
    existing = list(
        User.objects.exclude(from_location__isnull=True)
        .exclude(from_location="")
        .values_list("from_location", flat=True)
        .distinct()
        .order_by("from_location")
    )
    locations = existing if len(existing) >= 5 else FALLBACK_FROM_LOCATIONS
    rng = random.Random(seed)
    shuffled = list(locations)
    rng.shuffle(shuffled)
    return shuffled


def build_import_rows(raw_rows, men_photos, women_photos, seed):
    locations = get_from_locations(seed)
    men_index = 0
    women_index = 0
    import_rows = []

    for index, row in enumerate(raw_rows):
        rng = random.Random(stable_int(seed, row["username"], "profile"))
        if row["gender"] == "male":
            photo = men_photos[men_index]
            men_index += 1
            height = rng.randint(165, 200)
        else:
            photo = women_photos[women_index]
            women_index += 1
            height = rng.randint(150, 185)

        from_location = locations[stable_int(seed, row["username"], "from") % len(locations)]
        import_rows.append(
            ImportRow(
                row_number=row["row_number"],
                photo_index=row["photo_index"],
                first_name=row["first_name"],
                last_name=row["last_name"],
                username=row["username"],
                tagline=row["tagline"][:40],
                date_of_birth=row["date_of_birth"],
                live=row["live"],
                bio=row["bio"],
                answers=row["answers"],
                gender=row["gender"],
                height=height,
                from_location=from_location,
                photo_path=photo,
            )
        )

    return import_rows


def normalize_to_valid(value, valid_values):
    if value in valid_values:
        return value
    ordered = sorted(valid_values)
    return min(ordered, key=lambda candidate: (abs(candidate - value), candidate))


def normalize_education(value):
    if value <= 2:
        return 1
    if value == 3:
        return 3
    return 5


def normalize_have_kids(value):
    return 1 if value <= 3 else 5


def questions_by_number(questions):
    grouped = {}
    for question in questions:
        grouped.setdefault(question.question_number, []).append(question)
    for question_list in grouped.values():
        question_list.sort(key=lambda q: (q.group_number or 0, q.question_name or ""))
    return grouped


def question_values(question):
    values = [int(answer.value) for answer in question.answers.all()]
    if not values:
        raise CommandError(f"Question {question.id} has no QuestionAnswer values")
    return set(values)


def validate_value(question, value, open_to_all=False):
    if open_to_all and value == 6:
        return
    valid_values = question_values(question)
    if value not in valid_values:
        raise CommandError(
            f"Invalid answer {value} for question {question.question_number}/{question.group_number} "
            f"{question.question_name}; valid values are {sorted(valid_values)}"
        )


def build_mandatory_answers(import_row, mandatory_questions, seed=20260612):
    grouped = questions_by_number(mandatory_questions)
    planned = []

    def add(question, me, lf, lf_open=False, me_open=False):
        validate_value(question, me, me_open)
        validate_value(question, lf, lf_open)
        planned.append(PlannedAnswer(question, me, me_open, lf, lf_open))

    # 1 Relationship: CSV has only 1b. Use it as Me, no looking-for on hookup/date/partner.
    relationship_me = min(import_row.answers["1b"], 5)
    for question in grouped.get(1, []):
        add(question, normalize_to_valid(relationship_me, question_values(question)), 1)

    # 2 Gender.
    gender_lf = import_row.answers["2b"]
    for question in grouped.get(2, []):
        is_male_question = (question.question_name or "").lower() == "male"
        if import_row.gender == "male":
            me = 5 if is_male_question else 1
        else:
            me = 1 if is_male_question else 5

        if gender_lf == 6:
            add(question, me, 6, lf_open=True)
        else:
            same_gender = (import_row.gender == "male" and is_male_question) or (import_row.gender == "female" and not is_male_question)
            lf = 6 - gender_lf if same_gender else gender_lf
            add(question, me, normalize_to_valid(lf, question_values(question)))

    # 3 Ethnicity: choose one primary ethnicity row deterministically.
    ethnicity_questions = grouped.get(3, [])
    if ethnicity_questions:
        primary_index = stable_int(seed, import_row.username, "ethnicity") % len(ethnicity_questions)
        ethnicity_lf = import_row.answers["3b"]
        for index, question in enumerate(ethnicity_questions):
            me = import_row.answers["3a"] if index == primary_index else 1
            if ethnicity_lf == 6:
                add(question, normalize_to_valid(me, question_values(question)), 6, lf_open=True)
            else:
                add(
                    question,
                    normalize_to_valid(me, question_values(question)),
                    normalize_to_valid(ethnicity_lf, question_values(question)),
                )

    # 4 Education.
    education_me = normalize_education(import_row.answers["4a"])
    education_lf_raw = import_row.answers["4b"]
    for question in grouped.get(4, []):
        if education_lf_raw == 6:
            add(question, education_me, 6, lf_open=True)
        else:
            add(question, education_me, normalize_education(education_lf_raw))

    # 5 Diet.
    diet_lf = import_row.answers["5b"]
    for question in grouped.get(5, []):
        me = normalize_to_valid(import_row.answers["5a"], question_values(question))
        if diet_lf == 6:
            add(question, me, 6, lf_open=True)
        else:
            add(question, me, normalize_to_valid(diet_lf, question_values(question)))

    # 6, 8, 9 single direct questions.
    for number in (6, 8, 9):
        questions = grouped.get(number, [])
        if len(questions) != 1:
            raise CommandError(f"Expected one mandatory question for number {number}, found {len(questions)}")
        question = questions[0]
        lf = import_row.answers[f"{number}b"]
        me = normalize_to_valid(import_row.answers[f"{number}a"], question_values(question))
        if lf == 6:
            add(question, me, 6, lf_open=True)
        else:
            add(question, me, normalize_to_valid(lf, question_values(question)))

    # 7 Habits: yes/no style 1 or 5 only, with OTA allowed for looking-for.
    habits_me = 1 if import_row.answers["7a"] <= 3 else 5
    habits_lf_raw = import_row.answers["7b"]
    for question in grouped.get(7, []):
        if habits_lf_raw == 6:
            add(question, habits_me, 6, lf_open=True)
        else:
            habits_lf = 1 if habits_lf_raw <= 3 else 5
            add(question, habits_me, habits_lf)

    # 10 Kids: Have is 1/5, Want is 1-5; b=6 is OTA for both.
    kids_lf_raw = import_row.answers["10b"]
    for question in grouped.get(10, []):
        name = (question.question_name or "").lower()
        if name == "have":
            me = normalize_have_kids(import_row.answers["10a"])
            lf = normalize_have_kids(kids_lf_raw) if kids_lf_raw != 6 else 6
        else:
            me = normalize_to_valid(import_row.answers["10a"], question_values(question))
            lf = normalize_to_valid(kids_lf_raw, question_values(question)) if kids_lf_raw != 6 else 6
        add(question, me, lf, lf_open=(kids_lf_raw == 6))

    if len(planned) != EXPECTED_MANDATORY_QUESTION_COUNT:
        raise CommandError(
            f"Expected {EXPECTED_MANDATORY_QUESTION_COUNT} mandatory answers for {import_row.username}, "
            f"planned {len(planned)}."
        )

    seen = {answer.question.id for answer in planned}
    if len(seen) != len(planned):
        raise CommandError(f"Duplicate planned question for {import_row.username}")

    return planned


def make_blob_name(username, photo_path):
    digest = hashlib.sha256(photo_path.read_bytes()).hexdigest()[:12]
    extension = photo_path.suffix.lower().lstrip(".") or "jpg"
    return f"profile-photos/dummy-users/{username}-{digest}.{extension}"


def load_mandatory_questions():
    questions = list(
        Question.objects.filter(is_mandatory=True)
        .prefetch_related("answers")
        .order_by("question_number", "group_number", "question_name")
    )
    if len(questions) != EXPECTED_MANDATORY_QUESTION_COUNT:
        raise CommandError(
            f"Expected {EXPECTED_MANDATORY_QUESTION_COUNT} mandatory questions, found {len(questions)}."
        )
    return questions


class Command(BaseCommand):
    help = "Import the 1,000 dummy dating users from the provided CSV, photos, and mandatory answers."

    def add_arguments(self, parser):
        parser.add_argument("--csv", default=DEFAULT_CSV)
        parser.add_argument("--men-dir", default=DEFAULT_MEN_DIR)
        parser.add_argument("--women-dir", default=DEFAULT_WOMEN_DIR)
        parser.add_argument("--seed", type=int, default=20260612)
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--dry-run", action="store_true", help="Validate and print the import plan without writing data.")
        mode.add_argument("--commit", action="store_true", help="Create users, upload photos, and write answers.")

    def handle(self, *args, **options):
        commit = bool(options["commit"])
        raw_rows = read_dummy_csv(options["csv"])
        if len(raw_rows) != EXPECTED_USER_COUNT:
            raise CommandError(f"Expected {EXPECTED_USER_COUNT} data rows, found {len(raw_rows)}.")

        gender_counts = resolve_genders(raw_rows)
        adjusted_usernames = assign_unique_usernames(raw_rows)

        men_photos = list_usable_photos(options["men_dir"])
        women_photos = list_usable_photos(options["women_dir"])
        if len(men_photos) < EXPECTED_GENDER_COUNT:
            raise CommandError(f"Need at least {EXPECTED_GENDER_COUNT} usable men photos, found {len(men_photos)}.")
        if len(women_photos) < EXPECTED_GENDER_COUNT:
            raise CommandError(f"Need at least {EXPECTED_GENDER_COUNT} usable women photos, found {len(women_photos)}.")

        uploader = AzureUploader.from_environment()
        uploader.validate()

        mandatory_questions = load_mandatory_questions()
        import_rows = build_import_rows(raw_rows, men_photos, women_photos, options["seed"])

        total_answers = 0
        for import_row in import_rows:
            total_answers += len(build_mandatory_answers(import_row, mandatory_questions, options["seed"]))

        override_names = sorted(name for name in GENDER_OVERRIDES if any(row["first_name"] == name for row in raw_rows))
        self.stdout.write("Dummy user import plan")
        self.stdout.write(f"  CSV rows: {len(import_rows)}")
        self.stdout.write(f"  Gender split: {gender_counts['male']} men, {gender_counts['female']} women")
        self.stdout.write(f"  Photos: {EXPECTED_GENDER_COUNT} men, {EXPECTED_GENDER_COUNT} women planned")
        self.stdout.write(f"  Mandatory questions: {len(mandatory_questions)}")
        self.stdout.write(f"  Mandatory answers: {total_answers}")
        self.stdout.write(f"  Azure container: {uploader.container_name}")
        self.stdout.write(f"  Adjusted duplicate/existing usernames: {adjusted_usernames}")
        if override_names:
            self.stdout.write(f"  Gender overrides: {', '.join(override_names)}")

        if not commit:
            self.stdout.write(self.style.WARNING("Dry run only. Re-run with --commit to write data."))
            return

        created = 0
        uploaded = 0
        with transaction.atomic():
            for import_row in import_rows:
                blob_name = make_blob_name(import_row.username, import_row.photo_path)
                photo_url = uploader.upload(import_row.photo_path, blob_name)
                uploaded += 1

                user = User.objects.create(
                    username=import_row.username,
                    email=f"{import_row.username}@{DUMMY_EMAIL_DOMAIN}",
                    is_dummy=True,
                    password=make_password(None),
                    first_name=import_row.first_name,
                    last_name=import_row.last_name,
                    age=calculate_age(import_row.date_of_birth),
                    date_of_birth=import_row.date_of_birth,
                    height=import_row.height,
                    from_location=import_row.from_location,
                    live=import_row.live,
                    tagline=import_row.tagline,
                    bio=import_row.bio,
                    profile_photo=photo_url,
                    last_active=timezone.now(),
                )
                UserPicture.objects.create(user=user, image_url=photo_url, order=0)

                answers = build_mandatory_answers(import_row, mandatory_questions, options["seed"])
                UserAnswer.objects.bulk_create([
                    UserAnswer(
                        user=user,
                        question=answer.question,
                        me_answer=answer.me_answer,
                        me_open_to_all=answer.me_open_to_all,
                        me_importance=3,
                        me_share=True,
                        looking_for_answer=answer.looking_for_answer,
                        looking_for_open_to_all=answer.looking_for_open_to_all,
                        looking_for_importance=3,
                        looking_for_share=True,
                        excluded_answer_values=[],
                    )
                    for answer in answers
                ])
                UserRequiredQuestion.objects.bulk_create([
                    UserRequiredQuestion(user=user, question=answer.question)
                    for answer in answers
                ])
                User.objects.filter(id=user.id).update(questions_answered_count=len(answers))
                created += 1

        self.stdout.write(self.style.SUCCESS(
            f"Imported {created} users, uploaded {uploaded} photos, and created {total_answers} mandatory answers."
        ))
