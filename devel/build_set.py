#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import unicode_literals
import unicodecsv as csv
import json
import codecs
import re
from argparse import ArgumentParser


class Inst(object):
    """This holds a general CSV line, with all CSV fields as attributes of the object."""

    def __init__(self, data, headers):
        """Initialize, storing the given CSV headers and initializing using the given data
        (in the same order as the headers).

        @param data: a list of data fields, a line as read by Python CSV module
        @param headers: a list of corresponding field names, e.g., CSV header as read by Python \
            CSV module
        """
        self.__headers = headers
        for attr, val in zip(headers, data):
            setattr(self, attr, val)

    def as_array(self):
        """Return the values as an array, in the order given by the current headers (which were
        provided upon object construction)."""
        ret = []
        for attr in self.__headers:
            ret.append(getattr(self, attr, ''))
        return ret

    def as_dict(self):
        """Return the values as a dictionary, with keys for field names and values for the
        corresponding values."""
        ret = {}
        for attr in self.__headers:
            ret[attr] = getattr(self, attr, '')
        return ret


def read_file(file_name):
    ret = []
    with codecs.open(file_name, 'rb', 'UTF-8') as fh:
        for line in fh:
            ret.append(line.rstrip('\r\n'))
    return ret


def process_files(args):
    # read the data
    texts = read_file(args.in_texts)
    delex_texts = read_file(args.in_delex_texts)
    das = read_file(args.in_das)
    delex_das = read_file(args.in_delex_das)

    # process the data
    headers = ['da', 'text', 'delex_da', 'delex_text']
    insts = []

    for text, delex_text, da, delex_da in zip(texts, delex_texts, das, delex_das):
        if args.skip_hello and da == 'hello()':  # skip repetitive hello() DAs
            continue
        delex_text = re.sub(r'(X-[^ /]+)/[^ ]*', r'\1', delex_text)  # remove synt. form indicators
        insts.append(Inst([da, text, delex_da, delex_text], headers))

    # write CSV
    with open(args.out_file + '.csv', 'wb') as fh:
        # starting with the header
        csvwrite = csv.writer(fh, delimiter=b",", lineterminator="\n", encoding="UTF-8")
        csvwrite.writerow(headers)
        for inst in insts:
            csvwrite.writerow(inst.as_array())

    # write JSON
    with codecs.open(args.out_file + '.json', 'wb', 'UTF-8') as fh:
        data = [inst.as_dict() for inst in insts]
        json.dump(data, fh, ensure_ascii=False, indent=4, sort_keys=True)


def main():

    ap = ArgumentParser()

    ap.add_argument('-s', '--skip-hello', help='Ignore hello() DAs', action='store_true')

    ap.add_argument('in_texts', type=str, help='Input lexicalized texts')
    ap.add_argument('in_delex_texts', type=str, help='Input delexicalized texts')

    ap.add_argument('in_das', type=str, help='Input lexicalized DAs')
    ap.add_argument('in_delex_das', type=str, help='Input delexicalized DAs')

    ap.add_argument('out_file', type=str,
                    help='Output file (without extension, CSV and JSON will be added)')

    args = ap.parse_args()

    process_files(args)


if __name__ == '__main__':
    main()
