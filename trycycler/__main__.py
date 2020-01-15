#!/usr/bin/env python3
"""
Copyright 2019 Ryan Wick (rrwick@gmail.com)
https://github.com/rrwick/Trycycler

This file is part of Trycycler. Trycycler is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by the Free Software Foundation,
either version 3 of the License, or (at your option) any later version. Trycycler is distributed
in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
details. You should have received a copy of the GNU General Public License along with Trycycler.
If not, see <http://www.gnu.org/licenses/>.
"""

import argparse
import pathlib
import random
import string
import sys

from .base_scores import get_per_base_scores
from .circularisation import circularise
from .consensus import get_consensus_seq
from .help_formatter import MyParser, MyHelpFormatter
from .initial_check import initial_sanity_check
from .log import log, section_header, explanation
from .misc import get_default_thread_count, get_sequence_file_type, load_fasta, get_fastq_stats
from .pairwise import get_pairwise_alignments
from .starting_seq import get_starting_seq, rotate_to_starting_seq
from .version import __version__
from . import settings


def get_arguments(args):
    parser = MyParser(description='Trycycler', add_help=False, formatter_class=MyHelpFormatter)

    required_args = parser.add_argument_group('Required arguments')
    required_args.add_argument('-c', '--contigs', type=str, required=True, nargs='+',
                               help='Input contigs to be reconciled (multiple FASTA files '
                                    'required with one contig per file)')
    required_args.add_argument('-r', '--reads', type=str, required=True,
                               help='Long reads (FASTQ format) used to generate the assemblies')
    required_args.add_argument('-o', '--out_dir', type=pathlib.Path, required=True,
                               help='Output directory')

    setting_args = parser.add_argument_group('Settings')
    setting_args.add_argument('-t', '--threads', type=int, default=get_default_thread_count(),
                              help='Number of threads to use for alignment')
    setting_args.add_argument('--not_circular', action='store_true',
                              help='The input contigs are not circular (default: assume the input '
                                   'contigs are circular)')

    other_args = parser.add_argument_group('Other')
    other_args.add_argument('-h', '--help', action='help', default=argparse.SUPPRESS,
                            help='Show this help message and exit')
    other_args.add_argument('--version', action='version',
                            version='Trycycler v' + __version__,
                            help="Show program's version number and exit")

    args = parser.parse_args(args)
    args.circular = not args.not_circular
    return args


def main(args=None):
    args = get_arguments(args)
    random.seed(0)
    welcome_message()
    check_inputs_and_requirements(args)
    seqs = load_contig_sequences(args.contigs)
    initial_sanity_check(seqs)
    starting_seq, seqs = get_starting_seq(seqs, args.threads)
    if args.circular:
        seqs = circularise(seqs, args.reads, args.threads)
        seqs = rotate_to_starting_seq(seqs, starting_seq)
    save_seqs_to_fasta(seqs, args.out_dir / '01_all_seqs.fasta')
    per_base_scores = get_per_base_scores(seqs, args.reads, args.circular)
    pairwise_alignments = get_pairwise_alignments(seqs)
    consensus_seq = get_consensus_seq(seqs, per_base_scores, pairwise_alignments)
    save_seqs_to_fasta(consensus_seq, args.out_dir / '02_consensus.fasta')


def welcome_message():
    section_header('Starting Trycycler')
    explanation('Trycycler is a tool for combining multiple genome assemblies from the same '
                'long-read set (e.g. assemblies from different assemblers) into a consensus '
                'assembly that takes the best parts of each.')


def check_inputs_and_requirements(args):
    check_input_reads(args.reads)
    check_input_contigs(args.contigs)
    check_output_directory(args.out_dir)
    check_required_software()


def load_contig_sequences(filenames):
    contig_seqs = {}
    for i, f in enumerate(filenames):
        letter = string.ascii_uppercase[i]
        seqs = load_fasta(f)
        assert len(seqs) == 1
        contig_seqs[letter] = seqs[0][1]
    return contig_seqs


def check_input_reads(filename):
    read_type = get_sequence_file_type(filename)
    if read_type != 'FASTQ':
        sys.exit(f'Error: input reads ({filename}) are not in FASTQ format')
    log(f'Input reads: {filename}')
    read_count, total_size, n50 = get_fastq_stats(filename)
    log(f'  {read_count:,} reads ({total_size:,} bp)')
    log(f'  N50 = {n50:,} bp')
    log()


def check_input_contigs(filenames):
    if len(filenames) < 2:
        sys.exit('Error: two or more input contigs are required')
    if len(filenames) > settings.MAX_INPUT_CONTIGS:
        sys.exit(f'Error: you cannot have more than {settings.MAX_INPUT_CONTIGS} input contigs')
    log(f'Input contigs:')
    contig_names = set()
    for i, f in enumerate(filenames):
        contig_type = get_sequence_file_type(f)
        if contig_type != 'FASTA':
            sys.exit(f'Error: input contig file ({f}) is not in FASTA format')
        seqs = load_fasta(f)
        if len(seqs) == 0:
            sys.exit(f'Error: input contig file ({f}) contains no sequences')
        if len(seqs) > 1:
            sys.exit(f'Error: input contig file ({f}) contains multiple sequences')
        contig_name = seqs[0][0]
        if contig_name in contig_names:
            sys.exit(f'Error: duplicate contig name: {contig_name}')
        contig_names.add(contig_name)
        contig_len = len(seqs[0][1])
        letter = string.ascii_uppercase[i]
        log(f'  {letter}: {f} ({contig_name}: {contig_len:,} bp)')
    log()


def check_output_directory(directory):
    if directory.is_file():
        sys.exit(f'Error: output directory ({directory}) already exists as a file')
    if directory.is_dir():
        log(f'Output directory ({directory}) already exists - files may be overwritten.')
    else:
        log(f'Creating output directory: {directory}')
        directory.mkdir(parents=True)
    log()


def check_required_software():
    pass
    # TODO
    # TODO
    # TODO
    # TODO
    # TODO


def save_seqs_to_fasta(seqs, filename):
    log(f'Saving sequences to file: {filename}')
    with open(filename, 'wt') as fasta:
        for name, seq in seqs.items():
            fasta.write(f'>{name}\n')
            fasta.write(f'{seq}\n')
    log()


if __name__ == '__main__':
    main()