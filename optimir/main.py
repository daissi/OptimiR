#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Florian THIBORD : florian.thibord@inserm.fr
# (17/11/17)
########################################################
#                  OptimiR PIPELINE                    #
########################################################
"""
### Pipeline for miRSeq data ###
Description todo

### Use example ###
./OPTIMIR --fq /path/to/sample.fq(.gz) --vcf /path/to/genotypes.vcf --dir_output /path/to/output/dir/
"""


# Standard libraries
import sys, os, time
from argparse import ArgumentParser
import subprocess
from pysam import AlignmentFile

# Personal libraries
from optimir.libs.essentials import *
from optimir.libs.library_preparation import prepare_library
from optimir.libs.pre_process import *
from optimir.libs.mapping import *
from optimir.libs.post_process import post_process_main

### MAIN
def main():
    ## OptimiR path:
    optimiR_path = os.path.abspath(os.path.dirname(__file__))
    
    ## Parsing arguments
    parser = ArgumentParser(description="OptimiR: A bioinformatics pipeline designed to detect and quantify miRNAs, isomiRs and polymiRs from miRSeq data, & study the impact of genetic variations on polymiRs' expression")
    ## Mandatory arguments : fastq file, vcf file (optional but strongly advised), output directory
    parser.add_argument("-i", "--fq", dest="FASTQ", default=None, required=True, help="Full path of the sample fastq file (accepted formats and extensions: fastq, fq and fq.gz)")
    parser.add_argument("-o", "--dirOutput", dest="OUTDIR", default="./OptimiR/", required=False, help="Full path of the directory where output files are generated [default: ./OptimiR/]")
    parser.add_argument("-g", "--vcf", dest="VCF", default=None, required=False, help="Full path of the vcf file with genotypes")

    ## Alignment & Score Parameters : seedLen, weight5, scoreThresh
    parser.add_argument("--seedLen", dest="SEEDLEN", type=int, default=17, required=False, help="Choose the alignment seed length used in option '-L' by Bowtie2 [default: 17]")
    parser.add_argument("--w5", dest="WEIGHT5", type=int, default=4, required=False, help="Choose the weight applied on events detected on the 5' end of aligned reads [default: 4]")
    parser.add_argument("--scoreThresh", dest="SCORE_THRESH", type=int, default=9, required=False, help="Choose the threshold for alignment score above which alignments are discarded [default: 9]")
    parser.add_argument("--consistentRate", dest="INCONSISTENT_THRESHOLD", type=float, default=0.01, required=False, help="Choose the rate threshold for inconsistent reads mapped to a polymiR above which the alignment is flagged as highly suspicious [default: 0.01]")

    ## Optionnal arguments : rmTempFiles, annot, adapt 3', adapt 5', readMin, readMax, bqTresh, trimAgain
    parser.add_argument("--rmTempFiles", dest="RMTEMP", default=False, required=False, action='store_true', help="Add this option to remove temporary files (trimmed fastq, collapsed fastq, mapped reads, annotated bams")
    parser.add_argument("--annot", dest="ANNOT_FILES", default="hpics", required=False, help="Control which annotation file is produced by adding corresponding letter : 'h' for expressed_hairpins, 'p' for polymiRs_table, 'i' for consistency_table, 'c' for remaining_ambiguous, 's' for isomiRs_dist. Ex: '--annot hpics' [default] will produce all of them")
    parser.add_argument("--gff_out", dest="WRITE_GFF", default=False, required=False, action='store_true', help="Add this option to generate results in mirGFF3 format [default : False]")
    parser.add_argument("--vcf_out", dest="WRITE_VCF", default=False, required=False, action='store_true', help="Add this option to generate results in VCF format [default : False]")
    parser.add_argument("--adapt3", dest="ADAPT3", default="AGATCGGAAGAGCACACGTCTGAACTCCAGTCAC -a TGGAATTCTCGGGTGCCAAGG", required=False, help="Define the 3' adaptor sequence (default is NEB & ILLUMINA: AGATCGGAAGAGCACACGTCTGAACTCCAGTCAC -a TGGAATTCTCGGGTGCCAAGG -> hack: use -a to add adapter sequences)")
    parser.add_argument("--adapt5", dest="ADAPT5", default="ATCTACACGTTCAGAGTTCTACAGTCCGACGATC", required=False, help="Define the 5' adaptor sequence (default is NEB: ATCTACACGTTCAGAGTTCTACAGTCCGACGATC)")
    parser.add_argument("--readMin", dest="READMIN", type=int, default=15, required=False, help="Define the minimum read length defined with option -m in cutadapt [default: 15]")
    parser.add_argument("--readMax", dest="READMAX", type=int, default=27, required=False, help="Define the maximum read length defined with option -M in cutadapt [default: 27]")
    parser.add_argument("--bqThresh", dest="BQTHRESH", type=int, default=28, required=False, help="Define the Base Quality threshold defined with option -q in cutadapt [default: 28]")
    parser.add_argument("--trimAgain", dest="TRIM_AGAIN", default=False, required=False, action='store_true', help="Add this option to trim files that have been trimmed in a previous application. By default, when temporary files are kept, trimmed files are reused. If you wish to change a paramater used in the trimming step of the workflow, this parameter is a must.")

    ## Optionnal arguments concerning the miRBase library used: matures.fa, hairpins.fa, miRs_coords.gff3. Usefull to switch from miRBase to miRCarta, or a new version of the miRBase
    parser.add_argument("--maturesFasta", dest="MATURES", default="{}/resources/fasta/hsa_matures_miRBase_v21.fa".format(optimiR_path), required=False, help="Path to the reference library containing mature miRNAs sequences [default: miRBase 21]")
    parser.add_argument("--hairpinsFasta", dest="HAIRPINS", default="{}/resources/fasta/hsa_hairpins_miRBase_v21.fa".format(optimiR_path), required=False, help="Path to the reference library containing pri-miRNAs sequences [default: miRBase 21]")
    parser.add_argument("--gff3", dest="GFF3", default="{}/resources/coordinates/hsa_miRBase_v21.gff3".format(optimiR_path), required=False, help="Path to the reference library containing miRNAs and pri-miRNAs coordinates [default: miRBase v21, GRCh38 coordinates]")

    parser.add_argument("--quiet", dest="VERBOSE", default=True, required=False, action='store_false', help="Add this option to remove OptimiR progression on screen [default: activated]")

    ## Optionnal paths to cutadapt, bowtie2 and samtools (mandatory if not in $PATH)
    parser.add_argument("--cutadapt", dest="CUTADAPT", default="cutadapt", required=False, help="Provide path to the cutadapt binary [default: from $PATH]")
    parser.add_argument("--bowtie2", dest="BOWTIE2", default="bowtie2", required=False, help="Provide path to the bowtie2 binary [default: from $PATH]")
    parser.add_argument("--bowtie2_build", dest="BOWTIE2_BUILD", default="bowtie2-build", required=False, help="Provide path to the bowtie2 index builder binary [default: from $PATH]")
    parser.add_argument("--samtools", dest="SAMTOOLS", default="samtools", required=False, help="Provide path to the samtools binary [default: from $PATH]")

    ## Assign arguments to variables (all caps for variables corresponding to args)
    args = parser.parse_args()
    FASTQ = args.FASTQ
    VCF = args.VCF
    OUTDIR = args.OUTDIR
    SEEDLEN = args.SEEDLEN
    WEIGHT5 = args.WEIGHT5
    SCORE_THRESHOLD = args.SCORE_THRESH
    INCONSISTENT_THRESHOLD = args.INCONSISTENT_THRESHOLD
    RMTEMP = args.RMTEMP
    ANNOT_FILES = args.ANNOT_FILES
    WRITE_GFF = args.WRITE_GFF
    WRITE_VCF = args.WRITE_VCF
    ADAPT3 = args.ADAPT3
    ADAPT5 = args.ADAPT5    
    READMIN = args.READMIN
    READMAX = args.READMAX
    BQTHRESH = args.BQTHRESH
    TRIM_AGAIN = args.TRIM_AGAIN
    MATURES = args.MATURES
    HAIRPINS = args.HAIRPINS
    GFF3 = args.GFF3
    VERBOSE = args.VERBOSE
    CUTADAPT = args.CUTADAPT
    BOWTIE2 = args.BOWTIE2
    BOWTIE2_BUILD = args.BOWTIE2_BUILD
    SAMTOOLS = args.SAMTOOLS

    try:
        if VCF == None:
            VCF_AVAIL = False
            if WRITE_VCF:
                print("WARNING: no variant provided, thus no VCF output will be generated\n")
                WRITE_VCF = False
        else:
            check_if_file_exists(VCF)
        check_if_file_exists(MATURES)
        check_if_file_exists(HAIRPINS)
        check_if_file_exists(GFF3)
        check_if_file_exists(FASTQ)
        
    except InputError as err:
        print("ERROR during library preparation: file {} does not exists. Check input filename and try again.\n".format(err.input_name))
        sys.exit(4)
    
    if OUTDIR[-1] == "/":
        OUTDIR = OUTDIR[:-1]
    tmpdir = os.path.abspath(OUTDIR) + "/OptimiR_tmp"
    
    ########################
    ##    MAIN PROCESS    ##
    ########################

    try:
        start = time.time()
        subprocess.call("mkdir -p " + OUTDIR, shell=True)
        subprocess.call("mkdir -p " + tmpdir, shell=True)
        sample_name = os.path.basename(FASTQ)
        sample_name = sample_name.split('.')[0] ## remove extension
        fun_str_progress([sample_name], "header", VERBOSE) ## print header
        ##############################
        # LIBRARY PREPARATION
        # Create directory where OptimiR files will be stored
        out_directory = os.path.abspath(OUTDIR) + "/OptimiR_lib/"
        # Create directory for OptimiR fasta library
        fasta_dir =  out_directory + "fasta/"
        subprocess.call("mkdir -p " + fasta_dir, shell=True)
        fasta_file = fasta_dir + "optimiR_library.fa"
        # Create directory and path for bowtie2 index alignment
        index_dir =  out_directory + "bowtie2_index/"
        subprocess.call("mkdir -p " + index_dir, shell=True)
        index_path = index_dir + "optimiR_alignment_library"
        # Create directory for pickle objects
        pickle_dir = out_directory + "pickle/"
        subprocess.call("mkdir -p " + pickle_dir, shell=True)
        lib_infos_pickle_path = pickle_dir + "lib_infos.pkl"
        d_OptimiR_pickle_path = pickle_dir + "d_OptimiR.pkl"
        # in this directory, the new library is created
        prepare_library(BOWTIE2_BUILD, VCF, MATURES, HAIRPINS, GFF3, out_directory, fasta_file, index_path, lib_infos_pickle_path, d_OptimiR_pickle_path)
        VCF_AVAILABLE, GENO_AVAILABLE, sample_list, fasta_hash, vcf_hash = load_obj(lib_infos_pickle_path)
        if GENO_AVAILABLE and not(sample_name in sample_list):
            print("WARNING : Sample provided {} does not match any genotyped sample in provided vcf file".format(sample_name))
            GENO_AVAILABLE = False
        lp_time = time.time()
        fun_str_progress([VCF_AVAILABLE, GENO_AVAILABLE, lp_time - start], "lib_prep", VERBOSE)
        ##############################
        # PRE ALIGNMENT PROCESS : Adapter trimming / Size selection + Read collapsing
        tmpdir_trim = tmpdir + '/0_Trimming'
        if not(os.path.exists(tmpdir_trim + "/" + sample_name + ".trimmed.fq")) or TRIM_AGAIN:
            subprocess.call('mkdir -p {}'.format(tmpdir_trim), shell=True)
            trimming(FASTQ, sample_name, tmpdir_trim, CUTADAPT, ADAPT3, ADAPT5, READMIN, READMAX, BQTHRESH)
        trimming_time = time.time()
        fun_str_progress([trimming_time - lp_time], "trim", VERBOSE)
        tmpdir_collapsed = tmpdir + '/1_Collapsing'
        subprocess.call('mkdir -p {}'.format(tmpdir_collapsed), shell=True)
        collapse_table, collapse_report = collapsing(sample_name, tmpdir_collapsed, tmpdir_trim)
        collapsing_time = time.time()
        fun_str_progress([collapsing_time - trimming_time], "collaps", VERBOSE)
        ##############################
        # ALIGNMENT : local mode on index_path library
        tmpdir_mapping = tmpdir + '/2_Mapping'
        subprocess.call('mkdir -p {}'.format(tmpdir_mapping), shell=True)
        fastq_in = '{}/{}.clpsd.fq'.format(tmpdir_collapsed, sample_name)
        mapping(tmpdir_mapping, fastq_in, sample_name, BOWTIE2, SEEDLEN, index_path, optimiR_path, SAMTOOLS)
        mapping_time = time.time()
        fun_str_progress([mapping_time - collapsing_time], "mapping", VERBOSE)
        ##############################
        # POST ALIGNMENT PROCESS : Read Annotation + Genotype Consistance + Alignment Scoring + Abundances generation
        tmpdir_postProcess = tmpdir + "/3_PostProcess"
        subprocess.call("mkdir -p {}".format(tmpdir_postProcess), shell=True)
        dir_results = OUTDIR + "/OptimiR_Results"
        subprocess.call("mkdir -p {}".format(dir_results), shell=True)
        sourceDB = MATURES.split('/')[-1].split('.')[0]
        post_process_main(tmpdir_mapping, tmpdir_postProcess, dir_results, collapse_table, sample_name, WEIGHT5, SCORE_THRESHOLD, INCONSISTENT_THRESHOLD, d_OptimiR_pickle_path, VCF_AVAILABLE, GENO_AVAILABLE, ANNOT_FILES, VERBOSE, WRITE_GFF, WRITE_VCF, sourceDB)
        pp_time = time.time()
        fun_str_progress([pp_time - mapping_time], "postproc", VERBOSE)
        end = time.time()
        if RMTEMP:
            subprocess.call("rm -r {}".format(tmpdir), shell=True)
        fun_str_progress([OUTDIR + "/OptimiR_Results/", end - start], "footer", VERBOSE)
    except Except_OS_Pipe as e:
        print('Error with system call: {}\nCheck that path to Bowtie2, Cutadapt, Samtools are well defined.\n'.format(e))
        exit(3)