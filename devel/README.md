Dataset translation process
===========================

* Required:
    * Python 2.7, Python 3.6 (for the last step)
    * [KenLM](http://kheafield.com/code/kenlm/) with Python support
    * [Morphodita 1.9+](https://github.com/ufal/morphodita) with Python support
    * [recordclass](https://pypi.python.org/pypi/recordclass) Python module
    * [TGen](https://github.com/UFAL-DSG/tgen)

''Localize'' the data to prepare for translations
-----------------------------------------------

```
    ./localize.py source/all-text.txt source/all-abst.txt source/all-das.txt source/all-loc.txt source/all-da_loc.txt
```

Translate localized data
------------------------

* This must be done manually.
* Add sentence IDs `<s id="XX"></s>` to preserve connection to DAs:
```
    cat all-loc.txt | perl -e 'my $ctr = 0; while (my $line = <>){ chomp $line; print "<s id=$ctr>$line</s>\n"; $ctr++ }' > all-loc.num.txt
```
* Also, a list of surface forms must be prepared for the localized slot values (`surface_forms.json`).
* The `delexicalize.py` script checks whether all information from the DA is present in the translation
    * If values are not found, they must be either added to `surface_forms.json` according to the
      translated sentence, or the translated sentence must be fixed.


Build delexicalized lowercased language model
---------------------------------------------

* to score different translations of the same DA to determine what should be multiplied
* assuming sentence IDs at start of each line (from translations), otherwise skip 1st line
```
    cat translations.txt | sed 's/^<s id=[0-9]\+>//;s/<\/s>$//' > translations.plain.txt
    ./delexicalize.py \
        -s name,area,address,phone,good_for_meal,near,food,price_range,count,price,postcode 
        -f ../surface_forms.json \
        -t czech-morfflex-pdt-160310.tagger \
        -l translated/translations.plain.txt \
        source/all-da_loc.txt translated/delex-lemmas.txt
    cd translated
    cat delex-lemmas.txt | \
        perl -pe 's/([.,!;?])(?!NEG)/ $1/g;s/ +/ /g; my @toks; foreach $tok (split / /){ if ($tok =~ /^X-/){ push @toks, $tok } else { $tok = lc $tok; $tok =~ s/\.neg$/\.NEG/; push @toks, $tok } } $_ = join " ", @toks;' \
        > delex-lemmas.lc.tok.txt
```

* Use KenLM:

```
   /path/to/kenlm/build/bin/lmplz -o 5 -S 15G -T /tmp/ < delex-lemmas.lc.tok.txt > delex-lm.arpa
   /path/to/kenlm/build/bin/build_binary delex-lm.arpa delex-lm.bin
```    


Expand translated data (with different lexicalizations)
-------------------------------------------------------

* Use Morphodita for tagging, with a handcrafted list of overrides (`tagger_overrides.json`).
* Use the language model built in the previous step.
    * KenLM Python support is required.

```    
    ./expand.py -l translated/delex-lm.bin \
        -s name,area,address,phone,good_for_meal,near,food,price_range,count,price,postcode \
        -f ../surface_forms.json \
        -t czech-morfflex-pdt-160310.tagger \
        -o translated/tagger_overrides.json \
        source/all-das.txt source/all-da_loc.txt translated/translations.plain.txt \
        translated/expand-texts.txt translated/expand-delex_texts.txt translated/expand-das.txt translated/expand-delex_das.txt
```

* The resulting data must be checked manually (no agreement checking in the code).
    * Data to be checked are marked with _CHECK_ at the start of the line.
* The delexicalized versions produced by the script contain a rough information about the 
  syntactic form; this is too inaccurate and has been removed from the final version.

Build final CSV & JSON files
----------------------------

* Ignore the `hello()` lines, they are repetitive and handcrafted anyway
    * They actually haven't been used by Wen et al. in the original experiments, although they are
      present in their set.

```
    ./build_set.py --skip-hello \
        translated/expand-{texts,delex_texts,das,delex_das}.txt \
        dataset
```

Split train/dev/test
--------------------

* The split needs to contain different DAs in different sections, this script ensures it (see main [README](../README.md) for details). 
    It also delexicalizes the data once more, to account for changes after expansions.

```
    ./split_set.py -s 3:1:1 \
        -a name,area,address,phone,good_for_meal,near,food,price_range,count,price,postcode \
        czech-morfflex-pdt-160310.tagger \
        ../surface_forms.json dataset.json \
        train,devel,test
    mv train.json devel.json test.json ..
```

