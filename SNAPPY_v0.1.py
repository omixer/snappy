"""
assign_chrY_hg.py, by Alissa Severson, with Jonathan A. Shortt

This script takes chrY data in plink format (.bim, .bed, .fam) and produces haplogroup assignments. It should be
run in the same directory as the plink files, and the only given argument is the project name or prefix to the files.

ex:
python3 assign_chrY_hg.py oceania-males

Currently, the ref_files are expected to be in the same directory as the data, so if that is not the case the paths
will need to be updated. Two output files are produced, with default names chrY_hgs.out and chrY_hgs.all. chrY_hgs.out 
contains the assignments and chrY_hgs.all lists all haplogroups with at least one snp present, and the accompanying 
score as a reference. Please don't hesitate to get in touch with questions!
"""


import os
import os.path
import sys
import subprocess
import parse_ref_files
import parse_plink_files
import argparse

def count_define_called_snps(subgroup_snps, pos_to_gt, isogg_id_to_pos):
    """counts how many defining snps are actually called"""
    total = 0
    for snp in subgroup_snps:
        # if multiple ids for the same snp, tests until finds one with position
        if '/' in snp:
            candidates = snp.split('/')
            for candidate in candidates:
                if candidate in isogg_id_to_pos:
                    snp = candidate
                    break
        # if the snp is genotyped, count it
        if snp in isogg_id_to_pos:
            pos = isogg_id_to_pos[snp]
            if pos in pos_to_gt:
                gt = pos_to_gt[pos]
                if gt != 'N':
                    total += 1
    return float(total)


def get_parent_hg(hg_to_parent, hg):
    """returns the parental haplogroup"""
    if hg in hg_to_parent:
        return hg_to_parent[hg]
    elif hg in ['A0-T', 'A00']:
        return ''
    else:
        return hg[:-1]


def has_parent_calls(hg, sample, scores, names, parent_dict):
    """check if at least the parent or grandparent hg has a derived genotype"""
    count_present = 0   # keeps track of whether parent or grandparent hg is derived
    for i in range(2):
        hg = get_parent_hg(parent_dict, hg)     # get parental hg
        if hg in names:
            hg_index = names.index(hg)
            if scores[sample, hg_index] > 0:    # check if hg snps are derived
                count_present += 1

    if count_present > 0:
        return True
    else:
        return False


def get_ancestry(hg, parent_dict):
    """create list of all parent haplogroups"""
    hg = get_parent_hg(parent_dict, hg)
    ancestors = []
    while hg:
        ancestors.append(hg)
        hg = get_parent_hg(parent_dict, hg)

    return ancestors


def score_hgs(hg_scores, hg_to_snps, genotypes, n, issog_id_to_pos, group_to_parent):
    """
    score every hg for an individual using the counts recorded in hg_score, calculate what fraction of snps and
    ancestral snps are derived
    """
    hg_names = list(hg_to_snps.keys())
    strict_hg_to_score = dict()     # only score hgs with derived parent or grandparent hg
    all_hg_to_score = dict()        # score all hgs
    for h in range(len(hg_names)):
        hg_score = hg_scores[n, h]  # get number of derived calls for hg snps
        if hg_score > 0:
            hg = hg_names[h]
            n_called_snps = 0
            n_defining_snps = 0
            while hg:               # count number of derived snps in hg and all ancestral hgs
                if hg in hg_names:
                    n_called_snps += hg_scores[n, hg_names.index(hg)]
                    n_defining_snps += count_define_called_snps(hg_to_snps[hg], genotypes[n], issog_id_to_pos)

                hg = get_parent_hg(group_to_parent, hg)

            # record hg score
            if n_defining_snps > 0:
                all_hg_to_score[hg_names[h]] = n_called_snps / float(n_defining_snps)
                if has_parent_calls(hg_names[h], n, hg_scores, hg_names, group_to_parent):
                    strict_hg_to_score[hg_names[h]] = n_called_snps / float(n_defining_snps)

    # return hg scores
    if strict_hg_to_score.keys():
        return strict_hg_to_score
    else:
        return all_hg_to_score


def pick_leaf(hg_to_score, group_to_parent, outfile, sample_id, min_hap_score, min_deep_score, hg_to_snps):
    """
    of the non-zero scored haplogroups collect all of the leaves, ie those which are not ancestral to any other
    non-zero haplogroup. Then, choose the group with the highest score and longest name
    """
    candidates = hg_to_score.keys()
    if not candidates:  # no hg matches, likely a poor quality sample
        print('No match: ' + sample_id)
        outfile.write(sample_id + '\tno match\n')
        return

    # get list of all leaf hgs
    #leaves = [candidates[0]]
    #for c in range(1, len(candidates)):
    leaves = []
    for c in range(0, len(candidates)):
        candidate = candidates[c]
        c_ancestors = get_ancestry(candidate, group_to_parent)
        if hg_to_score[candidate] >= min_hap_score and c_ancestors:     # check if hg score is high enough and is not the root
            is_leaf = True
            bad_leaves = []
            for leaf in leaves:         # check whether candidate hg is ancestor of leaf, or leaf ancestor of candidate
                l_ancestors = get_ancestry(leaf, group_to_parent)
                if candidate in l_ancestors:
                    is_leaf = False
                if leaf in c_ancestors:
                    bad_leaves.append(leaf)
            for l in bad_leaves:
                leaves.remove(l)
            if is_leaf:
                leaves.append(candidate)

    max_leaf = 'A0-T'
    max_score = 0
    try:
    	max_score = hg_to_score[max_leaf]
    except:
    	max_score = 0
    if leaves:
    	# find leaf with highest hg score
    	max_score = hg_to_score[leaves[0]]
    	max_leaf = leaves[0]
    	for leaf in leaves:
        	if max_score < hg_to_score[leaf]:
        		max_leaf = leaf
        		max_score = hg_to_score[leaf]

    	# check if there is a deeper leaf with a high score
    	longest_leaf = max(leaves, key=len)
    	if len(max_leaf) < len(longest_leaf) and hg_to_score[longest_leaf] >= min_deep_score: 
        	max_leaf = longest_leaf
        	max_score = hg_to_score[longest_leaf]
    elif max_score < min_hap_score:
    	print '%s: No supported leaf haplogroup available. Assigning default root haplogroup A0-T' % (sample_id)
    #else:
    	#print '%s: No supported leaf haplogroup available. Assigning default root haplogroup A0-T' % (sample_id)
        
        
    # write to output file
    hg_snps = ','.join(hg_to_snps[max_leaf])
    outfile.write('%s\t%s\t%s\t%s\n' % (sample_id, max_leaf, str(round(max_score, 3)), hg_snps))


def get_all_subgroups(hg_to_score, fi, sample_id):
    """record all non-zero scored haplogroups as a reference"""
    top_candidates = []
    candidate_scores = []
    all_scores = hg_to_score.values()
    while all_scores:       # order hgs based on score
        max_score = max(all_scores)

        candidates = []
        for hg in hg_to_score:
            if hg_to_score[hg] == max_score:
                candidates.append(hg)

        candidates.sort(key=len)
        candidates.reverse()

        for candidate in candidates:
            top_candidates.append(candidate)
            candidate_scores.append(max_score)

        while max_score in all_scores:
            all_scores.remove(max_score)

    # write hgs and scores to output
    line = []
    for i in range(len(top_candidates)):
        line.append(top_candidates[i] + ':' + str(round(candidate_scores[i], 3)))
    fi.write(str(sample_id) + '\t' + '\t'.join(line) + '\n')


def assign_subgroups(path, samples, hg_scores, hg_to_snps, genotypes, issog_id_to_pos, sample_id, min_hap_score , min_deep_score, out_prefix):
    """For a sample, score all the hgs based on # derived alleles, then assign hg"""
    print '\nNow finding best-supported haplogroup for each individual'
    print 'Minimum considered haplogroup score = %s' % (min_hap_score)
    print 'Minimum switch to deeper node score (min_deep_score) = %s' % (min_deep_score)
    # create a dictionary that sends a hg to its parent hg
    group_to_parent = dict()
    with open(path + '/ref_files/tree_structure.txt', 'r') as weird_hgs:
        for line in weird_hgs:
            line = line.rstrip('\n').split('\t')
            group_to_parent[line[0]] = line[1]

    # score all hgs, then use to assign hg to individual
    with open(path + '/' + out_prefix + '.out', 'w') as leaf_outfile, open(path + '/' + out_prefix + '.all', 'w') as all_outfile:
        print '\nPrinting results to .out and .all with prefix "%s"' % (out_prefix)
        for n in range(samples):
            hg_to_score = score_hgs(hg_scores, hg_to_snps, genotypes, n, issog_id_to_pos, group_to_parent)
            pick_leaf(hg_to_score, group_to_parent, leaf_outfile, sample_id[n], min_hap_score , min_deep_score, hg_to_snps)
            get_all_subgroups(hg_to_score, all_outfile, sample_id[n])


def main(args):
    path = os.getcwd()
    project_name = args.infile
    raw = path + '/' + project_name + '.raw'

    # create .raw plink file to interpret genotypes from binary files
    if not os.path.isfile(raw):
    	print 'Using plink to create .raw file'
    	subprocess.call(['plink', '--bfile', project_name, '--recodeAD', '--out', project_name])
    else:
    	print 'Using %s for genotype input' % (raw)

    # build reference dictionaries
    der_allele_dict = parse_ref_files.build_derived_allele_dict(path)
    bim_id_dict, bim_allele_dict = parse_ref_files.build_bim_id_dict(path, project_name)
    hg_snp_dict = parse_ref_files.build_hg_snp_dict(path)
    issog_id_dict = parse_ref_files.build_isogg_id_dict(path)

    # get the genotype calls for each sample
    genotypes = []
    sample_ids = []
    n_individuals = 0
    with open(raw, 'r') as raw_data:
        bim_snp_ids = raw_data.readline().rstrip('\n').split(' ')[6:]
        for line in raw_data:
            line = line.rstrip('\n').split(' ')
            sample_id = line[1]
            sample_ids.append(sample_id)

            data = line[6:]
            genotype = parse_plink_files.get_individual_gt(bim_allele_dict, bim_id_dict, bim_snp_ids, data)
            genotypes.append(genotype)
            n_individuals += 1

    # use genotype calls to track number of derived snps called for a hg
    haplogroup_score, hg_snp_dict = parse_plink_files.tally_defining_snps(n_individuals, genotypes, hg_snp_dict,
                                                                          issog_id_dict, der_allele_dict)
    # assign samples to hg
    assign_subgroups(path, n_individuals, haplogroup_score, hg_snp_dict, genotypes, issog_id_dict, sample_ids, args.min_hap_score , args.min_deep_score, args.out)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    
    parser.add_argument('--infile', help='prefix to plink library', required=True)
    parser.add_argument('--min_hap_score', help='.out file from SNAPPY', nargs='?', const=1, type=float, default=0.6, required=False)
    parser.add_argument('--min_deep_score', help='minimum score to switch to deeper node for final assignment', nargs='?', const=1, type=float, default=0.8, required=False)
    parser.add_argument('--out', help='prefix for file output', nargs='?', const=1, type=str, default='chrY_hgs', required=False)
    
    args = parser.parse_args()
    main(args)
    sys.exit()
main()
