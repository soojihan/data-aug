import torch
import allennlp
import h5py
from allennlp.modules.token_embedders import ElmoTokenEmbedder
from allennlp.data.token_indexers import TokenIndexer, SingleIdTokenIndexer, ELMoTokenCharactersIndexer
from allennlp.data.vocabulary import Vocabulary

from allennlp.modules.text_field_embedders import BasicTextFieldEmbedder
from allennlp.modules.seq2vec_encoders import Seq2VecEncoder, PytorchSeq2VecWrapper
from allennlp.commands.elmo import ElmoEmbedder
from allennlp.data.dataset_readers import DatasetReader

import scipy as sp
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import time
import os
import pandas as pd
import sys
import json
import pickle
from nltk import word_tokenize
from pprint import pprint as pp

import operator
import csv
import string
from credbankprocessor import preprocessing_tweet_text
from preprocessing import text_preprocessor

from ast import literal_eval # convert string list to actual list
from nltk import TweetTokenizer
from semeval.semeval_data_processor import load_csv
from simsem_eval import eval
import nltk
from nltk.corpus import stopwords
from nltk import WordNetLemmatizer
from ast import literal_eval
import argparse
from glob import glob
import re
import random
from sys import platform


pd.set_option('display.expand_frame_repr', False)
pd.set_option('display.max_columns', None)
pd.options.mode.chained_assignment = None


def semeval_sem_sim(cand_emd, ref_emd):
    f1 = h5py.File(cand_emd, 'r')
    print("Keys: %s" % len(f1.keys()))

    f2 = h5py.File(ref_emd, 'r')
    print("Keys: %s" % len(f2.keys()))

    sim_scores=[]
    tweet_id = []
    gold_labels= []

    data = load_data(name='semeval')
    print(list(data))

    for i, k in enumerate(f1.keys()):
        if i%500==0:
            print(i)

        if k != 'sentence_to_index':
            int_id = int(k)
            label = data.loc[int_id]['goldlabel']
            gold_labels.append(label)
            text1 = np.average(f1[(k)], axis=0).reshape(1,-1)
            text2 = np.average(f2[(k)], axis=0).reshape(1,-1)
            assert text1.shape[1]==text2.shape[1]

            if not (np.isnan(text1).any()) and not (np.isnan(text2).any()):
                score = cosine_similarity(text1, text2)
                sim_scores.append(score.flatten()[0])
                tweet_id.append(k)
                # if score.flatten()[0] >= 0.673580:
                #     print(i, cand_id, score.flatten()[0])
            else:
                score = 0
                sim_scores.append(0)
                tweet_id.append(k)
            # if i==10:
            #     break
    df = pd.DataFrame()
    df['sim_score']=sim_scores
    df['id']=tweet_id
    df['label']=gold_labels
    print(df.head())
    df.sort_values(by=['id'],ascending=True)
    print(df.head())
    outfile = os.path.abspath(os.path.join(os.path.dirname(__file__), '..',  'data/semeval2015/file-embed-output/5.5b-avg'))
    df.to_csv(os.path.join(outfile, 'score.csv'))

def pheme_sem_sim(cand_emd, ref_emd, cand_empty, ref_empty, newdf_path, score_path):

    ## Load ELMo embedding dictionaries
    f1 = h5py.File(cand_emd, 'r')
    print("Keys: %s" % len(f1.keys()))

    f2 = h5py.File(ref_emd, 'r')
    print("Keys: %s" % len(f2.keys()))

    ## Load candidates and references
    ref, cand = load_data(name="pheme")
    if cand_empty:
        cand = cand.drop(cand_empty)
        cand.reset_index(inplace=True, drop=False)
        cand.to_csv(os.path.join(newdf_path, 'dropped_candidates.csv')) # Save the dropped dataframe

    if ref_empty: ## Drop empty references
        ref = ref.drop(ref_empty)
        ref.reset_index(inplace=True, drop=False)
        ref.to_csv(os.path.join(newdf_path, 'dropped_ref.csv'))

    assert len(cand) == (len(f1.keys())-1) # dropped df length is equal to the # of keys in embeddings (-1: sentence to index)
    assert len(ref) == (len(f2.keys()) - 1)

    for i, ref_k in enumerate(f2.keys()): # Iterate reference embeddings
        sim_scores = []
        tweet_id = []
        print(i)
        for j, cand_k in enumerate(f1.keys()):
            if j % 1000 ==0:
                print(j)
            if (ref_k != 'sentence_to_index') and (cand_k!='sentence_to_index'):

                ref_id = int(ref_k)
                cand_id = int(cand_k)
                text1 = np.average(f1[(cand_k)], axis=0).reshape(1, -1)
                text2 = np.average(f2[(ref_k)], axis=0).reshape(1, -1)
                assert text1.shape[1] == text2.shape[1]

                if not (np.isnan(text1).any()) and not (np.isnan(text2).any()):
                    score = cosine_similarity(text1, text2)
                    sim_scores.append(score.flatten()[0])
                    tweet_id.append(cand_id)
                    # if score.flatten()[0] >= 0.673580:
                    #     print(i, cand_id, score.flatten()[0])
                else:
                    score = 0
                    sim_scores.append(0)
                    tweet_id.append(cand_id)
                # if i==10:
                #     break
        df = pd.DataFrame()
        df['sim_score'] = sim_scores
        df['id'] = tweet_id
        print(df.head())
        df.sort_values(by=['id'], ascending=True)
        print(df.head())
        df.to_csv(os.path.join(score_path,'ref-{}_score.csv'.format(ref_k))) # Save scores per reference tweet

def load_data(event, batch_num=None):
    """
    Load preprocessed candidates and references
    :param event:
    :return:
    """
    if platform == 'linux':
        dpath = '/mnt/fastdata/acp16sh/data-aug/data_augmentation/data/data_hydrator/file-embed-input/{}'.format(event)
    elif platform == 'darwin':
        dpath = os.path.join('..', 'data_augmentation/data_hydrator/file-embed-input/{}'.format(event))

    # batch_size = 788900

    cand = os.path.join(dpath, 'input-cand-processed_{}.pickle'.format(batch_num)) # charliehebdo
    # cand = os.path.join(dpath, 'input-cand-user-processed-part2.pickle') # ferguson
    with open(os.path.join(cand), 'rb') as tf:
        cand = pickle.load(tf)
        # print(len(cand[:3155558]))
        # print(len(cand[3155557:]))
        # cand = cand[:3155558]
        # print(batch_num * batch_size, (batch_num + 1) * batch_size)
        # if batch_num is not None: # ferguson
        #     cand = cand[batch_num * batch_size: (batch_num + 1) * batch_size]
        # cand = cand[3155557:]
        tf.close()
    print("Number of processed candidates: ", len(cand))

    ref = os.path.join(dpath, 'input-ref-processed.pickle')
    with open(os.path.join(ref), 'rb') as tf:
        ref = pickle.load(tf)
        tf.close()
    print("Number of processed references: ", len(ref))

    return ref, cand

def hydrator_sem_sim(event, cand_emd, ref_emd,  score_path, batch_num =None):
    """
    Compute semantic relatedness of Hydrator tweets
    :param event:
    :param cand_emd:
    :param ref_emd:
    :param score_path:
    :return:
    """
    ## Load ELMo embedding dictionaries
    f1 = h5py.File(cand_emd, 'r')
    # f1 = h5py.File(open(cand_emd, 'rb'), 'r')
    print("Keys: %s" % len(f1.keys()))

    f2 = h5py.File(ref_emd, 'r')
    print("Keys: %s" % len(f2.keys()))

    ## Load candidates and references
    if batch_num is not None:
        ref, cand = load_data(event= event, batch_num=batch_num)
    else:
        ref, cand = load_data(event=event)
    print(len(cand))
    print((len(f1.keys())-1))
    assert len(cand) == (len(f1.keys())-1) # dropped df length is equal to the # of keys in embeddings (-1: sentence to index)
    assert len(ref) == (len(f2.keys())-1)

    for i, ref_k in enumerate(f2.keys()): # Iterate reference embeddings
        sim_scores = []
        tweet_id = []
        # print(i)
        for j, cand_k in enumerate(f1.keys()):
            # if j % 1000 ==0:
            #     print(j)
            if (ref_k != 'sentence_to_index') and (cand_k!='sentence_to_index'):
                ref_id = int(ref_k)
                cand_id = int(cand_k)
                text1 = np.average(f1[(cand_k)], axis=0).reshape(1, -1)
                text2 = np.average(f2[(ref_k)], axis=0).reshape(1, -1)
                assert text1.shape[1] == text2.shape[1]

                if not (np.isnan(text1).any()) and not (np.isnan(text2).any()):
                    score = cosine_similarity(text1, text2)
                    sim_scores.append(score.flatten()[0])
                    tweet_id.append(cand_id)
                    # if score.flatten()[0] >= 0.673580:
                    #     print(i, cand_id, score.flatten()[0])
                else:
                    score = 0
                    sim_scores.append(0)
                    tweet_id.append(cand_id)
                # if i==10:
                #     break
        df = pd.DataFrame()
        df['sim_score'] = sim_scores
        df['id'] = tweet_id
        # print(df.head())
        df.sort_values(by=['id'], ascending=True)
        df.to_csv(os.path.join(score_path,'ref-{}_score.csv'.format(ref_k))) # Save scores per reference tweet
        print("ref {} is done".format(ref_k))

def eval_results():
    """
    Evaluate results of SemEval task
    :return:
    """
    result_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..',  'data/semeval2015/file-embed-output/cred-avg/score.csv'))
    print(result_path)
    eval(result_path)


def main():
    if platform == 'darwin':
        event = 'germanwings'
        cand_emd = os.path.join('..',
                               'data_augmentation/data_hydrator/file-embed-output/{}/elmo-cand-output.hdf5'.format(event))

        ref_emd = os.path.join('..',
                                    'data_augmentation/data_hydrator/file-embed-output/{}/elmo-ref-output.hdf5'.format(event))
        score_path ='./test_elmo'
        batch_num=None
        # cand_emd = os.path.join(os.path.dirname(__file__), '..', 'data/semeval2015/file-embed-output/5.5b-avg/output-text1.hdf5')
        # ref_emd = os.path.join(os.path.dirname(__file__), '..', 'data/semeval2015/file-embed-output/5.5b-avg/output-text2.hdf5')
        # TODO: define arguments

    elif platform == 'linux':
        parser = argparse.ArgumentParser()
        parser.add_argument('--event', help='the name of event')
        parser.add_argument('--cand_emd', help='ELMo embeddings of candidates ')
        parser.add_argument('--ref_emd', help='ELMo embeddings of references')
        parser.add_argument('--score_path', help='path to save semantic relatedness scores')
        parser.add_argument('--batch_num', help='elmo batch number')
        # parser.add_argument('--tweet_path', help='Path to save dataframes after dropping empty tweets')
        # parser.add_argument('--empty_path', help='Indices of empty strings')

        args = parser.parse_args()
        event = args.event
        cand_emd = args.cand_emd
        ref_emd = args.ref_emd
        score_path = args.score_path
        batch_num = int(args.batch_num)
        os.makedirs(score_path, exist_ok=True)
        # newdf_path = args.tweet_path
        # empty_indice_path = args.empty_path
        print(cand_emd)
        print(ref_emd)
    # hydrator_sem_sim(event, cand_emd, ref_emd, score_path)
    hydrator_sem_sim(event, cand_emd, ref_emd, score_path, batch_num)

    # semeval_sem_sim(cand_emd, ref_emd)

    # cand_empty = empty_indices(event=event, t='candidates', action='load')
    # ref_empty = empty_indices(event=event, t='ref', action='load')

if __name__ == '__main__':
    main()
    # eval_results()
# event= 'ferguson'
# ref, cand = load_data(event= event)
# print()