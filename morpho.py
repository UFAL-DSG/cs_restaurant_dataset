#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import unicode_literals

from ufal.morphodita import Tagger, Forms, TaggedLemmas, TokenRanges, Morpho, TaggedLemmasForms
import re

class Analyzer(object):
    """Morphodita analyzer/tagger wrapper."""

    def __init__(self, tagger_model):
        self.__tagger = Tagger.load(tagger_model)
        self.__tokenizer = self.__tagger.newTokenizer()
        self.__forms_buf = Forms()
        self.__tokens_buf = TokenRanges()
        self.__lemmas_buf = TaggedLemmas()

    def analyze(self, stop_text):
        self.__tokenizer.setText(stop_text)
        out = []
        while self.__tokenizer.nextSentence(self.__forms_buf, self.__tokens_buf):
            self.__tagger.tag(self.__forms_buf, self.__lemmas_buf)
            out.extend([(form, lemma.lemma, lemma.tag)
                        for (form, lemma) in zip(self.__forms_buf, self.__lemmas_buf)])
        return out


def trunc_lemma(lemma):

    lemma_trunc = re.sub(r'((?:(`|_;|_:|_,|_\^|))+)(`|_;|_:|_,|_\^).+$', r'\1', lemma)
    if not lemma_trunc:
        lemma_trunc = lemma
    lemma_trunc = re.sub(r'(.+)-[0-9].*$', r'\1', lemma_trunc)
    return lemma_trunc
