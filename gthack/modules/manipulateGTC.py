from IlluminaBeadArrayFiles import *
import struct
from io import BytesIO
import os
import sys
import logging

'''
function: manipulate_gtc(self)
description: wrapper method to update metadata, snps, validate them and convert to bytes for writing
input: gtcFunction object
output: writes updated gtcs to output directory specified at runtime
'''
def manipulate_gtc(self):
    import gthack.modules.extractInformation as extractInformation
    import gthack.modules.write_gtc as write_gtc
    logger = logging.getLogger('manipulate_gtc')
    logger.debug('In method manipulate_gtc()')
    
    bpm=self.bpm
    bpm_csv=self.bpm_csv
    gtcDir=self.gtcDir
    outDir=self.outDir
    snpsToUpdate=self.snpUpdateFile
    overrides=self.overrides


    '''
    function: updateMetaData(data, metaData)
    description: update sample metadata (not snps) pertaining to sampleName, sentrixBarcode, plateName, well
    input: data dictionary of a sample gtc and the metadata line pertaining to that sample
    output: data dictionary with update information listed in meta data lines
    '''
    def updateMetaData(data, metaData):
        import itertools

        logger = logging.getLogger('updateMetaData')
        logger.debug("In sub-method of manipulate_gtc() -- updateMetaData()")
        dataDict = {}

        metaDataUpdates = metaData.rstrip().split(',')
        for update in metaDataUpdates:
            if update.rstrip().split('=')[0] == 'sampleName':
                dataDict[10] = update.rstrip().split('=')[1].encode()
            elif update.rstrip().split('=')[0] == 'sentrixBarcode':
                dataDict[1016] = update.rstrip().split('=')[1].encode()
            elif update.rstrip().split('=')[0] == 'plateName':
                dataDict[11] = update.rstrip().split('=')[1].encode()
            elif update.rstrip().split('=')[0] == 'well':
                dataDict[12] = update.rstrip().split('=')[1].encode()
            elif update.rstrip().split('=')[0] == 'sex':
                dataDict[1007] = update.rstrip().split('=')[1].encode()
            else:
                logger.warning(
                    'MetaData {} does not exist; please make sure spelling is correct and case sensitive!  Ignoring...'
                    .format(update.rstrip().split('=')[0]))
                print('MetaData {} does not exist; please make sure spelling is correct and case sensitive!  Ignoring...'
                    .format(update.rstrip().split('=')[0]))
                sys.stdout.flush()

        for key, value in dataDict.items():
            data[key] = value

        return data

    
    '''
    function: snpUpdate(data, line)
    description: updates the snps in a gtc if the input text-file indicates a snp needs to be updated
    input: data dictionary and a snp line in the text-file for the gtc sample
    output: returns data dictionary for that sample with updated snp (update both base call in bytes and genotype)
    '''
    def snpUpdate(data, line):
        logger = logging.getLogger('snpUpdate')
        logger.debug("In sub-method of manipulate_gtc() -- snpUpdate()")
        
        COMPLEMENT_MAP = dict(zip("ABCDGHKMRTVYNID", "TVGHCDMKYABRNID"))
        
        loc = manifest.names.index(line.rstrip().split()[0])
        manifest_name = manifest.names[loc]
        manifest_name_csv = manifest_csv.names[loc]
        assert manifest_name == manifest_name_csv


        manifestSnpsStr = manifest.snps[loc]
        manifestSnps = [manifestSnpsStr[1], manifestSnpsStr[-2]]
        if manifest.ref_strands[loc] == RefStrand.Minus:
            manifestSnps = [COMPLEMENT_MAP[snp] for snp in manifestSnps]


        newSnpsStr = str(line.rstrip().split()[1])
        newSnps = [newSnpsStr[0], newSnpsStr[1]]

        # Getting genotype byte
        if newSnps[0] != newSnps[1] and newSnps[0] != '-':
            data[1002][loc] = 2
        elif newSnps[0] == '-' and newSnps[1] == '-':
            data[1002][loc] = 0
            data[1003][loc] = '--'.encode()
        elif newSnps[0] == newSnps[1]:
            if newSnps[0] in manifestSnps:
                if newSnps[0] == manifestSnps[0]:
                    data[1002][loc] = 1
                else:
                    data[1002][loc] = 3
            else:
                newSnps = [COMPLEMENT_MAP[snp] for snp in newSnps]
                if newSnps[0] == manifestSnps[0]:
                    data[1002][loc] = 1
                else:
                    data[1002][loc] = 3
        else:
            print("NO CONDITION MET; SOMETHING IS WRONG")

        # Getting base call byte
        if data[1002][loc] == 0:
            data[1003][loc] = '--'.encode()
        else:
            if newSnps[0] in ['I', 'D']:
                if data[1002][loc] == 1:
                    data[1003][loc] = (manifestSnps[0] + manifestSnps[0]).encode()
                elif data[1002][loc] == 2:
                    data[1003][loc] = (manifestSnps[0] + manifestSnps[1]).encode()
                else:
                    data[1003][loc] = (manifestSnps[1] + manifestSnps[1]).encode()
            else:
                allele_a = manifest_csv.alleles[loc][0]
                allele_b = manifest_csv.alleles[loc][1]
                if data[1002][loc] == 1:
                    data[1003][loc] = (allele_a + allele_a).encode()
                elif data[1002][loc] == 2:
                    data[1003][loc] = (allele_a + allele_b).encode()
                else:
                    data[1003][loc] = (allele_b + allele_b).encode()
        return data

    
    '''
    function: validateUpdate(originalGTC, outputName, outDir)
    description: a function to validate the manipulated gtc against the original gtc it is based off
    input: requires the orginal gtc, the name of the new gtc, and the output directory
    output: None - Raises an AssertionError if a gtc fail validation and records in the log file and standard out
    '''
    def validateUpdate(originalGTC, outputName, outDir):
        import gthack.modules.extractInformation as extractInformation
        import gthack.modules.write_gtc as write_gtc


        logger = logging.getLogger('validateUpdate')
        logger.debug("In sub-method of manipulate_gtc() -- validateUpdate()")

        original_genotype = GenotypeCalls(originalGTC)
        gtc_copy = GenotypeCalls(os.path.join(outDir,'{}.gtc'.format(outputName)),check_write_complete=False)
        
        try:
            assert gtc_copy.get_autocall_date() == original_genotype.get_autocall_date()
            assert gtc_copy.get_autocall_version() == original_genotype.get_autocall_version()
            #assert gtc_copy.get_base_calls() == genotype_calls.get_base_calls() -- do not activate, will def fail if snps are changed
            assert gtc_copy.get_cluster_file() == original_genotype.get_cluster_file()
            assert (gtc_copy.get_control_x_intensities() ==original_genotype.get_control_x_intensities()).all()
            assert (gtc_copy.get_control_y_intensities() ==original_genotype.get_control_y_intensities()).all()
            assert gtc_copy.get_num_no_calls() == original_genotype.get_num_no_calls()
            #assert gtc_copy.get_gender() == original_genotype.get_gender()
            assert (gtc_copy.get_genotype_scores() ==original_genotype.get_genotype_scores()).all()
            #assert gtc_copy.get_genotypes() == genotype_calls.get_genotypes()  -- do not activate, will def fail if snps are changed
            assert gtc_copy.get_percentiles_x() == original_genotype.get_percentiles_x()
            assert (gtc_copy.get_raw_x_intensities() == original_genotype.get_raw_x_intensities()).all()

            all_genotypes = gtc_copy.get_genotypes()
            assert len(manifest.names) == len(all_genotypes)
            assert len(manifest.names) == len(gtc_copy.get_logr_ratios())
            assert len(manifest.names) == len(gtc_copy.get_ballele_freqs())

            logger.info(os.path.join(outDir, '{}.gtc'.format(outputName)) +' passed validation!')
            print(os.path.join(outDir, '{}.gtc'.format(outputName)) +' passed validation!')
            sys.stdout.flush()

        except AssertionError:
            logger.warning(os.path.join(outDir, '{}.gtc'.format(outputName)) +' failed validation -- please re-run this gtc')
            print(os.path.join(outDir, '{}.gtc'.format(outputName)) +' failed validation -- please re-run this gtc')
            sys.stdout.flush()
    
    '''
    function: snpOverride()
    description: will temporarily overwrite the original call in the bpm
    input: bpm manifest and a text-file gathered at run time containing snps name and override value
    output: returns an ephemeral bpm manifest used during the duration of the run only
    '''
    def snpOverride(manifest, overrides):
        logger = logging.getLogger('snpOverride')
        logger.debug('Opening snp override file...')
        
        with open(overrides, 'r') as snpsOverrides:
            for snp in snpsOverrides:
                snp = snp.split('\t')
                try:
                    logger.info('snp {} is being changed from {} to {}'.format(snp[0], manifest.snps[manifest.names.index(snp[0])], snp[1]))
                    manifest.snps[manifest.names.index(snp[0])] = snp[1].strip().encode()
                    logger.info('Success! Alleles of snp {} has been updated!'.format(snp[0]))
                except ValueError:
                    logger.error('Error! snp {} cannot be updated! Please check your input override file format.'.format(snp[0]))

        return manifest
    

###################################################################################################################
############### First analytic lines processed in manipulate_gtc(bpm, gtcDir, outDir, snpsToUpdate) ###############
###################################################################################################################
    logger.debug('Preparing to read in bpm file...')
    manifest = BeadPoolManifest(bpm)
    def get_manifest_csv():
        import csv

        def read_csv(file_path):
            with open(file_path) as f:
                reader = csv.reader(f)
                for i in range(7):
                    next(reader)
                header = next(reader)
                for row in reader:
                    yield dict(zip(header, row))


        file_path = self.bpm_csv
        # for row in read_csv(file_path):
        #     print(row.header)
        rows = list(read_csv(file_path))
        class Manifest:
            def __init__(self):
                self.names = []
                self.alleles = []

        manifest = Manifest()
        for row in rows:
            if 'Name' not in row or 'TopGenomicSeq' not in row:
                continue
            name = row['Name']
            top_genomic_seq = row['TopGenomicSeq']
            # get the string in top_genomic_seq which is in the format [alphabet/alphabet] and which will be in any index in the top_genomic_seq
            allele = 'NA'
            for i in range(len(top_genomic_seq) - 1):
                if top_genomic_seq[i] == '[' and top_genomic_seq[i + 4] == ']':
                    allele = top_genomic_seq[i + 1], top_genomic_seq[i + 3]
                    break
            manifest.names.append(name)
            manifest.alleles.append(allele)
        return manifest
    manifest_csv = get_manifest_csv()
    logger.debug('Successfully loaded BPM file')

    #######################
    # manifest overrides! #
    #######################
    if overrides == None:
        logger.debug('No overrides present')
    else:
        logger.debug('Override file present')
        manifest = snpOverride(manifest=manifest, overrides=overrides)
    
    gtc = ''
    total_gtcs = 0
    data = {}

    with open(snpsToUpdate) as updates:
        for line in updates:
            if line[0] == ">":
                total_gtcs += 1
                if total_gtcs == 1:
                    gtc = line.rstrip().split()[0][1:]
                    outputName = line.rstrip().split()[1]
                    data = extractInformation.getGtcInfo(gtc=os.path.join(gtcDir, gtc))
                    if len(line.rstrip().split()) == 3:  # means there is metadata to update
                        logger.info('Writing updated GTC to new GTC file...')
                        data = updateMetaData(data=data, metaData=line.rstrip().split()[2])
                else:
                    logger.info('Writing updated GTC to new GTC file...')
                    with open(os.path.join(outDir, '{}.gtc'.format(outputName)),"wb") as output_handle:
                        write_gtc.write_gtc(data, output_handle)

                    validateUpdate(originalGTC=os.path.join(gtcDir, gtc),
                                   outDir=outDir,
                                   outputName=outputName)

                    gtc = line.rstrip().split()[0][1:]
                    outputName = line.rstrip().split()[1]
                    data = extractInformation.getGtcInfo(gtc=os.path.join(gtcDir, gtc))
                    if len(line.rstrip().split()) == 3:  # means there is metadata to update
                        logger.info('Metadata found.  Updating metadata...')
                        data = updateMetaData(data=data, metaData=line.rstrip().split()[2])

            else:
                data = snpUpdate(data=data, line=line)

    # always the last gtc because out of lines in file at this point
    logger.info('Writing final updated GTC to new GTC file...')
    print('Writing final updated GTC to new GTC file...')
    sys.stdout.flush()
   
    with open(os.path.join(outDir, '{}.gtc'.format(outputName)),"wb") as output_handle:
        write_gtc.write_gtc(data, output_handle)

    validateUpdate(originalGTC=os.path.join(gtcDir, gtc),
                   outDir=outDir,
                   outputName=outputName)

    logger.info("All processing is finished!")
    print("All processing is finished!")
    sys.exit()