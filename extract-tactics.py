#!/usr/bin/env python3
import re
import sys
from itertools import chain
from bs4 import BeautifulSoup
from pyparsing import nestedExpr, ParseResults, ParseException

# The whole process:
# * Add the relevant \tacticdef, \vernacdef, \scopedef to the latex source
# * Move RefMan-mod to its own section, instead of being embedded in the middle of RefMan-ext
# * Call make doc-html
# * Call python3 ~/.emacs.d/lisp/own/company-coq/html-minify.py *.html from the
#   doc/refman/html folder
# * Call this script

TACTICS_PREPROCESSING = [('$n$', r'\n'), (r'\_', '_'), (r'\\', ''), (r'\{', 'LBRACE'), (r'\}', 'RBRACE'),
                         ('~', ' '), ("''", ''), ('``', ''), ('\\\n', '\n'), ('"', 'QUOTE')]

TACTICS_PREPROCESSING_RE = [(re.compile(r), s) for r, s in
                            [(r'\\([a-zA-Z]+) *{', r'{\\\1 '),
                             # (r'[_\^]{', r'{\\script '),
                             # (r'[_\^](.)', r'{\\script \1}'),
                             (r'\\ ', ' '),
                             (r'\$\\num', r'\\num$'),
                             (r'\$[^\$]*\$', ''), #TODO Check
                             (r'}{([\,])}', r' {\\separator \1}}'),
                             (r'([^\\])%.*', r'\1'),
                             (r'\\%', r'%'),
                             (r' *\.\.\.? *', r' \\ldots '),
                             (r'\\l?dots', r' \\ldots '),
                             (r' *([^a-zA-Z_<>!:\\]) *', r' \1 ')]] # This last one should be tokenizer options <- -> eqn: ! _

#TODO RefMan-pro

ABBREVS_POSTPROCESSING_RE = [(re.compile(r), s) for r, s in
                             [(r"([^\$\']) *([\[\(]+) *", r'\1 \2'),
                              (r' *([-=]) *> *', r' \1> '),
                              (r' *: *= *', r' := '),
                              (r' *< *- *', r' <- '),
                              (r' *> *- *> *', r' >-> '),
                              (r'([^\<])-(\|?) +', r'\1-\2'),
                              (r' *([\]\)\.\,\!]+) *', r'\1 '),
                              (r' *([\%]) *', r'\1'),
                              (r'eqn: *', 'eqn:'),
                              (r' *:= *', ' := '),
                              ('LBRACE', '{'),
                              ('RBRACE', '}'),
                              ('QUOTE', '"'),
                              (r'" *(@{[^"]+}) *"', r'"\1"'),
                              (r' *(\.?) *$', r'\1'),
                              (r'([^\\])"', r'\1\\"'),
                              ('  +', ' '),
                              ('^ +', ''),
                              (' +$', '')]]

ID_PATTERN = '@{([^{}]+)}'
ID_RE = re.compile(ID_PATTERN)
ID_ONLY_RE = re.compile("^" + ID_PATTERN + "$")
OPTION_RE = re.compile(r'\?\|([^\|]+)\|')

def behead(tup)           : return stringify(tup[1:])
def bebody(tup)           : return tup[:1]
def forget(_)             : return ()
def stringify(tup)        : return ' '.join(tup)

def optionify(tup):
    body = behead(tup)
    if ID_ONLY_RE.match(body):
        return body # YAS doesn't distinguish between optional and normal fields, and double-wrapping causes a bug
    else:
        return '?|{}|'.format(body)

def keywordize(tup):
    assert len(tup) == 2
    kwd = tup[1]
    if ID_RE.match(kwd):
        return kwd
    else:
        return '\\' + kwd.lstrip('\\')

def choicify(tup):
    choices = ' '.join(r'"' + choice + r'"' for choice in tup[1::2])
    return "@{{$$(yas-choose-value '({}))}}".format(choices)

ACTIONS = {'tt':          behead,
           'texttt':      behead,
           'mbox':        behead,
           'num':         bebody,
           'ident':       bebody,
           'term':        bebody,
           'vref':        bebody,
           'qualid':      bebody,
           'bindinglist': bebody,
           'binder':      bebody,
           'index':       forget,
           'tacindex':    forget,
           'comindex':    forget,
           'optindex':    forget,
           'label':       forget,
           'script':      forget,
           'separator':   forget, #TODO
           'textrm':      keywordize,
           'textit':      keywordize,
           'textsl':      keywordize,
           'rm\\sl':      keywordize, #TODO
           'sl':          keywordize,
           'em':          keywordize,
           'it':          keywordize,
           'nterm':       keywordize,
           'zeroone':     optionify,
           'argchoice':   choicify,
           'ldots':       stringify,
           'nelist':      behead,
           'nelistnosep': behead,
           'tacticdef':   behead}

QUICK_HELP_FILE = "./refman/quick-help.html"
BASE_PATH = "/build/coq/doc/refman/{}.tex"
TEMPLATE = './company-coq-abbrev.el.template'
OUTPUT = './company-coq-abbrev.el'
BASE_NAME = 'company-coq-abbrevs-{}'
DEFCONST = '(defconst {}\n  (list \n    {}))'

ALL_NAMES = ["RefMan-int", "RefMan-pre", "RefMan-gal", "RefMan-ext",
             "RefMan-mod", "RefMan-lib", "RefMan-cic", "RefMan-modr",
             "RefMan-oth", "RefMan-pro", "RefMan-tac", "RefMan-ltac",
             "RefMan-tacex", "RefMan-decl", "RefMan-syn", "RefMan-sch",
             "RefMan-com", "RefMan-uti", "RefMan-ide", "AddRefMan-pre", "Cases",
             "Coercion", "CanonicalStructures", "Classes", "Omega", "Micromega",
             "Extraction", "Program", "Polynom", "Nsatz", "Setoid",
             "AsyncProofs", "Universes", "Misc"]

# NAMES = ["RefMan-oth", "RefMan-tac", "RefMan-tacex", "Setoid", "Polynom",
#          "RefMan-lib", "Micromega", "Nsatz", "Extraction", "RefMan-ext",
#          "RefMan-syn"]

def preprocess_tactic(tactic):
    for pair in TACTICS_PREPROCESSING:
        tactic = tactic.replace(*pair)

    for r, sub in TACTICS_PREPROCESSING_RE:
        # print(tactic, "--", r, "--", r.sub(sub, tactic), "--")
        tactic = r.sub(sub, tactic)

    return tactic

def format_hole(kwd):
    placeholder = "@{{{}}}".format(kwd)
    return placeholder if kwd != 'str' else '"' + placeholder + '"'

def pluralize(ident):
    if not ID_ONLY_RE.match(ident):
        # print("Multi-patterns dot pattern:", ident)
        # raise ConversionError
        return ID_RE.sub(r'@{\1&}', ident)
    return ID_RE.sub(r'@{\1+}', ident)

def find_all(s, pattern):
    indices = []
    pos = -1
    while True:
        pos = s.find(pattern, pos + 1)
        if pos >= 0:
            indices.append(pos)
        else:
            break
    return indices

def replace_dot_pattern(s, pivot, pivot_pos, transform):
    left_end, right_start = pivot_pos, pivot_pos + len(pivot)
    for pattern_len in range(-left_end, 0):
        left_start, right_end = left_end + pattern_len, right_start - pattern_len
        if s[right_start:right_end] == s[left_start:left_end]:
            s = s[:left_start] + str(transform(s[left_start:left_end])) + s[right_end:]
            return s, True
    return s, False

def replace_dot_patterns(s, pivot, transform):
    while pivot in s:
        for pivot_pos in find_all(s, pivot):
            s, success = replace_dot_pattern(s, pivot, pivot_pos, transform)
            if success:
                break
        else:
            print("Invalid dots pattern:", s)
            raise ConversionError
    return s

def get_arg_variants(abbrev):
    if OPTION_RE.search(abbrev):
        return get_arg_variants(OPTION_RE.sub('', abbrev, 1)) + get_arg_variants(OPTION_RE.sub(r'\1', abbrev, 1))
    else:
        return (abbrev,)

OPT_VERNAC_RE = re.compile("Set ([A-Z])")

def get_set_variants(abbrev):
    if OPT_VERNAC_RE.match(abbrev):
        return (abbrev,
                ID_RE.sub('', OPT_VERNAC_RE.sub(r"Unset \1", abbrev, 1)),
                ID_RE.sub('', OPT_VERNAC_RE.sub(r"Test \1", abbrev, 1)))
    else:
        return (abbrev,)

def cleanup_abbrev(abbrev):
    for r, sub in ABBREVS_POSTPROCESSING_RE:
        abbrev = r.sub(sub, abbrev)
    return abbrev

def postprocess_abbrev(abbrev):
    abbrev = re.sub(r'[, ]*@{ldots}[, ]*', ' ... ', abbrev)
    abbrev = replace_dot_patterns(abbrev, ' ... ', pluralize)
    abbrevs = get_arg_variants(abbrev)
    abbrevs = tuple(map(cleanup_abbrev, abbrevs))
    abbrevs = tuple(chain(*(get_set_variants(abbrev) for abbrev in abbrevs)))
    abbrevs = tuple(map(cleanup_abbrev, abbrevs))
    abbrevs = tuple(tac for tac in abbrevs #TODO
                    if not ("@{|}" in abbrev or re.match("^selector: ", abbrev)))
    return abbrevs

def next_occ(doc, start, symbols):
    pos = None
    for symb in symbols:
        symb_pos = doc.find(symb, start)
        if symb_pos != -1 and (pos == None or 0 <= symb_pos < pos):
            pos = symb_pos
    if pos == None:
        raise ConversionError
    return pos

def find_instance(doc, start):
    try:
        depth, end = 0, start
        while depth >= 0:
            end = next_occ(doc, end + 1, '{}')
            if doc[end] == '{':
                depth += 1
            else:
                depth -= 1
        return end
    except ConversionError:
        print("No paren matching {}: {}".format(start, doc[start:start+20]))
        print("This is bad: numbers will be out of sync with the manual")
        raise

COMMENT_RE = re.compile(r'[^\\]%')
def is_comment(pos, doc):
    last_line_pos = max(0, doc.rfind('\n', 0, pos))
    comment = COMMENT_RE.match(doc, last_line_pos, pos)
    return bool(comment)

def find_instances(doc, command):
    end = 0
    while True:
        start = doc.find(command, end + 1)
        if start == -1:
            break

        if is_comment(start, doc):
            end = start + 1
        else:
            end = find_instance(doc, start)
            yield start, doc[start:end]

LABEL_MARKER = r"\label"
TACTIC_MARKERS = (r'\tacticdef', r'\vernacdef', r'\scopedef')

def find_tactics(doc):
    marker = TACTIC_MARKERS[0]

    for other_marker in TACTIC_MARKERS[1:]:
        doc = doc.replace(other_marker, marker)

    yield from find_instances(doc, marker)

def parse_to_sexp(parse):
    if isinstance(parse, ParseResults):
        return tuple(parse_to_sexp(x) for x in parse)
    else:
        return parse

NESTED_PARSER = nestedExpr(opener='{', closer='}')

def tactic_to_sexp(tactic):
    parse = NESTED_PARSER.parseString("{" + tactic + "}")
    tuplified = parse_to_sexp(parse)
    return tuplified[0]

class ConversionError(Exception):
    pass

def sexp_to_string(sexp):
    if not isinstance(sexp, tuple):
        if not isinstance(sexp, str):
            print("Invalid element:", sexp, file=sys.stderr)
            raise ConversionError
        if sexp[0] == '\\':
            sexp = format_hole(sexp[1:])
        return sexp

    if len(sexp) == 0:
        return None

    if len(sexp) == 1:
        return sexp_to_string(sexp[0])

    head = sexp[0]

    if head[0] != '\\':
        print("Invalid macro:", sexp, file=sys.stderr)
        raise ConversionError

    head = head[1:]
    if head not in ACTIONS:
        print("Unknown sexp:", sexp, file=sys.stderr)
        raise ConversionError

    sexp = tuple(sexp_to_string(arg) for arg in sexp)
    sexp = tuple(arg for arg in sexp if arg != None)
    sexp = ACTIONS[head](sexp)
    return sexp_to_string(sexp)

INDEX_MARKERS = (r'\tacindex', r'\comindex')

def tactic_to_abbrevs(pos, num, tactic):
    try:
        cleaned   = preprocess_tactic(tactic)
        sexp      = tactic_to_sexp(cleaned)
        preabbrev = sexp_to_string(sexp)
        abbrevs   = postprocess_abbrev(preabbrev)
        return tuple((num, abbrev) for abbrev in abbrevs)
    except (ConversionError, ParseException):
        print("{}: `{}...`".format(pos, tactic[:min(len(tactic), 40)].replace('\n', '')))
        return ()

def sort_uniq(abbrevs):
    abbrevs = sorted(abbrevs, key = lambda x: (x[1].lower(), x[0]))

    prev = None
    dedup = []
    for pos, abbrev in abbrevs:
        if abbrev == prev:
            continue
        dedup.append((pos, abbrev))
        prev = abbrev

    return dedup

def extract_abbrevs(doc, start_num):
    tactics = list(find_tactics(doc))
    abbrevs_groups = list(tactic_to_abbrevs(pos, start_num + num, tac)
                          for num, (pos, tac) in enumerate(tactics))
    abbrevs = list(chain(*abbrevs_groups))
    sorted_abbrevs = sort_uniq(abbrev for abbrev in abbrevs if abbrev != None)
    return start_num + len(tactics), sorted_abbrevs

def annotate(abbrevs, annotations):
    return [(abbrev, annotations[num])
            for num, abbrev in abbrevs]

QUICKHELP_RE = re.compile(r"^(?P<file>[a-z0-9]+)\.html#hevea_quickhelp(?P<num>[0-9]+)$")

def load_annotations(path):
    annots = {}
    with open(path, mode='rb') as html:
        soup = BeautifulSoup(html)
        for anchor in soup("a"):
            href = anchor['href']
            m = QUICKHELP_RE.match(href)
            if m:
                d = m.groupdict()
                annots[int(d["num"])] = (d["file"], d["num"])
    return annots

def main():
    abbrevs_by_chapter = {}
    annotations = load_annotations(QUICK_HELP_FILE)

    start_num = 0
    for name in ALL_NAMES: # sorted(NAMES, key=ALL_NAMES.index):
        print("Processing", name)
        with open(BASE_PATH.format(name)) as source:
            doc = source.read()
            start_num, abbrevs = extract_abbrevs(doc, start_num)
            annotated = annotate(abbrevs, annotations)
            abbrevs_by_chapter[name] = annotated
        print("{} entries found".format(len(abbrevs)))

    shortlist = DEFCONST.format(BASE_NAME.format("all"), ' '.join(BASE_NAME.format(name) for name in ALL_NAMES))

    defconsts = []
    for name in ALL_NAMES:
        lisp = "\n    ".join('\'("{}" . ("{}" . {}))'.format(abbrev, *annot)
                             for abbrev, annot in abbrevs_by_chapter[name])
        defconst = DEFCONST.format(BASE_NAME.format(name), lisp)
        defconsts.append(defconst)

    WRITE = True

    # idents = set()
    # for abbr in all_abbrevs:
    #     for match in ID_RE.findall(abbr):
    #         idents.add(re.sub(r"[ &\+]", '', match))
    # for ident in sorted(idents):
    #     print(r'\newcommand{{\{0}}}{{\emph{{{0}}}}}'.format(ident))

    if WRITE:
        with open(TEMPLATE) as template_f:
            template = template_f.read()

        template = template.replace('$ABBREVS$', '\n\n'.join(defconsts))
        template = template.replace('$SHORTLIST$', shortlist)

        with open(OUTPUT, mode='w') as output:
            output.write(template)
    else:
        for abbrev in sorted(abbrevs):
            print(abbrev)

main()

# TODO warn on missing dots