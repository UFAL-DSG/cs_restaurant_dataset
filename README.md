
''Localize'' the data to prepare for translations
-----------------------------------------------

``
    ./localize.py source/all-text.txt source/all-abst.txt source/all-das.txt source/all-loc.txt source/all-da_loc.txt
``

Build delexicalized lowercased language model
---------------------------------------------

* to score different translations of the same DA to determine what should be multiplied
* assuming sentence IDs at start of each line (from translations), otherwise skip 1st line
`` 
    cat translations.txt | sed 's/^<s id=[0-9]\+>//;s/<\/s>$//' > translations.plain.txt
    ./delexicalize.py \
        -s name,area,address,phone,good_for_meal,near,food,price_range,count,price,postcode 
        -f translated/surface_forms.json \
        -t czech-morfflex-pdt-160310.tagger \
        -l translated/translations.plain.txt \
        source/all-da_loc.txt translated/delex-lemmas.txt
    cd translated
    cat delex-lemmas.txt | \
        perl -pe 's/([.,!;?])(?!NEG)/ $1/g;s/ +/ /g; my @toks; foreach $tok (split / /){ if ($tok =~ /^X-/){ push @toks, $tok } else { $tok = lc $tok; $tok =~ s/\.neg$/\.NEG/; push @toks, $tok } } $_ = join " ", @toks;' \
        > delex-lemmas.lc.tok.txt
``

* Use KenLM:

``
    ~/work/tools/kenlm/build/bin/lmplz -o 5 -S 15G -T /tmp/ < delex-lemmas.lc.tok.txt > delex-lm.arpa
    ~/work/tools/kenlm/build/bin/build_binary delex-lm.arpa delex-lm.bin
``    


Expand translated data (with different lexicalizations)
-------------------------------------------------------

``    
    ./expand.py -l translated/delex-lm.bin \
        -s name,area,address,phone,good_for_meal,near,food,price_range,count,price,postcode \
        -f translated/surface_forms.json \
        -t czech-morfflex-pdt-160310.tagger \
        -o translated/tagger_overrides.json \
        source/all-das.txt source/all-da_loc.txt translated/translations.plain.txt \
        translated/expand-texts.txt translated/expand-delex_texts.txt translated/expand-das.txt translated/expand-delex_das.txt
``

* The resulting data must be checked manually (no agreement checking in the code)
* Data to be checked are marked

