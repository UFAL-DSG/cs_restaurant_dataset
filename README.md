Czech restaurant information dataset for NLG
============================================

* **Authors**: Ondřej Dušek, Filip Jurčíček, Josef Dvořák, Petra Grycová, Matěj Hejda, Jana Olivová, Michal Starý, Eva Štichová
* **License**: [Creative Commons 4.0 BY-SA](https://creativecommons.org/licenses/by-sa/4.0/)
* **LINDAT release**: TBD
* **Development website**: <https://github.com/UFAL-DSG/cs_restaurant_dataset>

This is a dataset for NLG in task-oriented spoken dialogue systems with Czech as the target 
language. It originated as a translation of the [English San Francisco Restaurants dataset by
Wen et al. (2015).](https://www.repository.cam.ac.uk/handle/1810/251304)

It includes input dialogue acts and the corresponding output natural language paraphrases in Czech.
Since the dataset is intended for RNN-based NLG systems using delexicalization, inflection tables
for all slot values appearing verbatim in the text are provided.

The dataset has been created from the English restaurant set using the following steps:
* Deduplicating identical sentences (with different slot DA values ignored)
* Localizing restaurant and neighborhood names to Prague (the actual data are random, do not correspond 
to any real restaurant database, but most of the proper names used included to be inflected in Czech)
* Translating the data into Czech
* Automatic checks for the presence of slot values
* Expanding the translated data to original size by relexicalizing with different slot values + manual checks

A more detailed description of the dataset and a publication is in the works.

Dataset format
--------------

The dataset is released in CSV and JSON formats (`dataset.csv`, `dataset.json`); the contents are
identical. Both files use the UTF-8 encoding.

The dataset contains 5192 instances. Each instance has the following properties:

* `da` -- the input dialogue act
* `delex_da` -- the input dialogue act, delexicalized
* `text` -- the output text
* `delex_text` -- the output text, delexicalized

The order of the instances is random to allow a simple training/development/test data split.

### The domain ###

The domain is restaurant information in Prague, with random/fictional values. The users may request
a specific restaurant, the system may ask for clarification or confirmation.

### Dialogue acts format ###

The dialogue acts in this dataset (`context_parse` and `response_da` properties) follow the [Alex
dialogue act format](https://github.com/UFAL-DSG/alex/blob/master/alex/doc/ufal-dialogue-acts.rst).
Basically, it is a sequence of *dialogue act items*. Each dialogue act item contains an act type
and may also contain a slot and a value.

**Examples**:

| dialogue act                                   | example utterance               | English translation                       |
| -----------------------------------------------|---------------------------------|-------------------------------------------|
| `goodbye()`                                    | *Na shledanou.*                 | _Goodbye._                                |
| `?request(food)`                               | *Na jaké jídlo máte chuť?*      | _What food type would you like?_          |
| `inform(area=Smíchov)&inform(name=\"Ananta\")` | *Ananta je v oblasti Smíchova.* | _Ananta is in the area of Smíchov._       |
| `?confirm(good_for_meal=dinner)`               | *Chcete restauraci na večeři?*  | _Would you like a restaurant for dinner?_ |

The **act types used** in this dataset are:
* `inform` -- informing about a restaurant or number of restaurants matching criteria
* `inform_only_match` -- informing about the only restaurant matching criteria
* `inform_no_match` -- apology that no match has been found
* `confirm` -- request to confirm a specific search parameter
* `select` -- request to select between two parameter values
* `request` -- request for additional details to complete the search
* `reqmore` -- asking whether the system can be of more help
* `goodbye` -- goodbye

**Slots used** in this dataset are:
* `name` -- restaurant name
* `type` -- venue type (the only value used here is `restaurant`)
* `price_range` -- restaurant price range (`cheap`, `moderate`, `expensive`)
* `price` -- the actual meal price (or price range) in Czech Crowns (Kč)
* `phone` -- restaurant phone number 
* `address` -- restaurant address (i.e., street and number)
* `postcode` -- restaurant postcode
* `area` -- the neighborhood in which the restaurant is located
* `near` -- a nearby other venue 
* `food` -- food type, i.e., cuisine (`Chinese`, `French`, etc.)
* `good_for_meal` -- suitability for a particular meal (`breakfast`, `lunch`, `brunch`, `dinner`)
* `kids_allowed` -- suitability for children

Acknowledgments
---------------

This work was funded by the Ministry of Education, Youth and Sports of the Czech Republic under
the grant agreement LK11221 and core research funding, SVV project 260 333, and GAUK grant 2058214
of Charles University in Prague. It used language resources stored and distributed by the
LINDAT/CLARIN project of the Ministry of Education, Youth and Sports of the Czech Republic
(project LM2015071).

