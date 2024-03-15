'''
Multitask BERT class, starter training code, evaluation, and test code.

Of note are:
* class MultitaskBERT: Your implementation of multitask BERT.
* function train_multitask: Training procedure for MultitaskBERT. Starter code
    copies training procedure from `classifier.py` (single-task SST).
* function test_multitask: Test procedure for MultitaskBERT. This function generates
    the required files for submission.

Running `python multitask_classifier.py` trains and tests your MultitaskBERT and
writes all required submission files.
'''

import random, numpy as np, argparse
from types import SimpleNamespace

import torch
from torch import nn
import torch.nn.functional as F
from torch.utils.data import DataLoader

from bert import BertModel
from optimizer import AdamW
from tqdm import tqdm
from pcgrad import PCGrad

from datasets import (
    SentenceClassificationDataset,
    SentenceClassificationTestDataset,
    SentencePairDataset,
    SentencePairTestDataset,
    load_multitask_data
)

from evaluation import model_eval_sst, model_eval_multitask, model_eval_test_multitask, model_eval_para, model_eval_sts


TQDM_DISABLE=False


# Fix the random seed.
def seed_everything(seed=11711):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True


BERT_HIDDEN_SIZE = 768
N_SENTIMENT_CLASSES = 5


class MultitaskBERT(nn.Module):
    '''
    This module should use BERT for 3 tasks:

    - Sentiment classification (predict_sentiment)
    - Paraphrase detection (predict_paraphrase)
    - Semantic Textual Similarity (predict_similarity)
    '''
    def __init__(self, config):
        super(MultitaskBERT, self).__init__()
        self.bert = BertModel.from_pretrained('bert-base-uncased')
        # Pretrain mode does not require updating BERT paramters.
        for param in self.bert.parameters():
            if config.option == 'pretrain':
                param.requires_grad = False
            elif config.option == 'finetune':
                param.requires_grad = True
        # You will want to add layers here to perform the downstream tasks.
        ### TODO
        self.dropout = torch.nn.Dropout(config.hidden_dropout_prob)
        self.fc = torch.nn.Linear(config.hidden_size, N_SENTIMENT_CLASSES)
        self.fc_paraphrase = torch.nn.Linear(config.hidden_size*2, 1)
        self.fc_similarity = torch.nn.Linear(config.hidden_size*2, 1)

    def forward(self, input_ids, attention_mask):
        'Takes a batch of sentences and produces embeddings for them.'
        # The final BERT embedding is the hidden state of [CLS] token (the first token)
        # Here, you can start by just returning the embeddings straight from BERT.
        # When thinking of improvements, you can later try modifying this
        # (e.g., by adding other layers).
        ### TODO
        outputs = self.bert(input_ids, attention_mask)
        pooler_output = outputs['pooler_output']
        return pooler_output


    def predict_sentiment(self, input_ids, attention_mask):
        '''Given a batch of sentences, outputs logits for classifying sentiment.
        There are 5 sentiment classes:
        (0 - negative, 1- somewhat negative, 2- neutral, 3- somewhat positive, 4- positive)
        Thus, your output should contain 5 logits for each sentence.
        '''
        ### TODO
        output = self.forward(input_ids, attention_mask)
        logits = self.fc(self.dropout(output))
        return logits


    def predict_paraphrase(self,
                           input_ids_1, attention_mask_1,
                           input_ids_2, attention_mask_2):
        '''Given a batch of pairs of sentences, outputs a single logit for predicting whether they are paraphrases.
        Note that your output should be unnormalized (a logit); it will be passed to the sigmoid function
        during evaluation.
        '''
        ### TODO
        output_1 = self.forward(input_ids_1, attention_mask_1)
        output_2 = self.forward(input_ids_2, attention_mask_2)
        #linear layer that outputs the same dimension, output dimension should be hidden size
        output = torch.cat((output_1, output_2), dim = 1)
        logits = self.fc_paraphrase(self.dropout(output))


        # output_1_norm = F.normalize(linear_1, p=2, dim=1)
        # output_2_norm = F.normalize(linear_2, p=2, dim=1)

        # # Compute cosine similarity
        # cosine_sim = torch.sum(output_1_norm * output_2_norm, dim=1)
        
        return logits
    


    def predict_similarity(self,
                           input_ids_1, attention_mask_1,
                           input_ids_2, attention_mask_2):
        '''Given a batch of pairs of sentences, outputs a single logit corresponding to how similar they are.
        Note that your output should be unnormalized (a logit).
        '''
        ### TODO
        output_1 = self.forward(input_ids_1, attention_mask_1)
        output_2 = self.forward(input_ids_2, attention_mask_2)

        output = torch.cat((output_1, output_2), dim = 1)
        logits = self.fc_similarity(self.dropout(output))
        # FC(torch.cat)

        # linear_1 = self.fc_similarity(self.dropout(output_1))
        # linear_2 = self.fc_similarity(self.dropout(output_2))

        # output_1_norm = F.normalize(linear_1, p=2, dim=1)
        # output_2_norm = F.normalize(linear_2, p=2, dim=1)
        
        # Compute cosine similarity
        # cosine_sim = torch.sum(output_1_norm * output_2_norm, dim=1)
        return logits


def save_model(model, optimizer, args, config, filepath):
    save_info = {
        'model': model.state_dict(),
        'optim': optimizer.state_dict(), 
        'args': args,
        'model_config': config,
        'system_rng': random.getstate(),
        'numpy_rng': np.random.get_state(),
        'torch_rng': torch.random.get_rng_state(),
    }

    torch.save(save_info, filepath)
    print(f"save the model to {filepath}")

## HELPER FUNCTION for train_multitask
def load_data(train_data, dev_data, args, type):
    if type == 'sst':
        train_data = SentenceClassificationDataset(train_data, args)
        dev_data = SentenceClassificationDataset(dev_data, args)
    else:
        train_data = SentencePairDataset(train_data, args)
        dev_data = SentencePairDataset(dev_data, args)

    train_dataloader = DataLoader(train_data, shuffle=True, batch_size=args.batch_size,
                                      collate_fn=train_data.collate_fn)
    dev_dataloader = DataLoader(dev_data, shuffle=False, batch_size=args.batch_size,
                                    collate_fn=dev_data.collate_fn)
    return train_dataloader, dev_dataloader

## HELPER FUNCTION: compute the cosine similarity of embeddings
def cosine_similarity_embedding(embed1, embed2, temp):
    return F.cosine_similarity(embed1, embed2, dim=-1) / temp 

## HELPER FUNCTION for train_multiple
def calculate_loss(batch, device, model, type, unsupervised=False, supervised =False):
    if type == 'sst':
        b_ids, b_mask, b_labels = (batch['token_ids'],
                                batch['attention_mask'], batch['labels'])
        
        b_ids = b_ids.to(device)
        b_mask = b_mask.to(device)
        b_labels = b_labels.to(device)

        if unsupervised:
            temp = 0.05
            embed1 = model.forward(b_ids, b_mask)
            embed2 = model.forward(b_ids,b_mask)
            cos_sim = cosine_similarity_embedding(embed1.unsqueeze(1), embed2.unsqueeze(0),temp = temp)
            loss_function = nn.CrossEntropyLoss()
            labels = torch.arange(cos_sim.size(0)).long().to(device)
            loss = loss_function(cos_sim,labels)
        else:
            logits = model.predict_sentiment(b_ids, b_mask)
            loss = F.cross_entropy(logits, b_labels.view(-1), reduction='sum') / args.batch_size
    
    else: # type == 'sts' or type == 'para'
        (b_ids1, b_mask1,
            b_ids2, b_mask2,
            b_labels, b_sent_ids) = (batch['token_ids_1'], batch['attention_mask_1'],
                        batch['token_ids_2'], batch['attention_mask_2'],
                        batch['labels'], batch['sent_ids'])

        b_ids1 = b_ids1.to(device)
        b_mask1 = b_mask1.to(device)
        b_ids2 = b_ids2.to(device)
        b_mask2 = b_mask2.to(device)
        b_labels = b_labels.to(device)

        if unsupervised == True:
            temp = 0.05
            embed1 = model.forward(b_ids1, b_mask1)
            embed2 = model.forward(b_ids1,b_mask1)
            embed3 = model.forward(b_ids2,b_mask2)
            embed4 = model.forward(b_ids2, b_mask2)
            cos_sim1 = cosine_similarity_embedding(embed1.unsqueeze(1), embed2.unsqueeze(0),temp = temp)
            cos_sim2 = cosine_similarity_embedding(embed3.unsqueeze(1), embed4.unsqueeze(0),temp = temp)

            loss_function = nn.CrossEntropyLoss()
            labels = torch.arange(cos_sim1.size(0)).long().to(device)
            loss = loss_function(cos_sim1,labels) + loss_function(cos_sim2,labels)
        elif supervised == True:
            temp = 0.05
            neutral_embed = model.forward(b_ids1, b_mask1)           
            positive_embed = model.forward(b_ids2, b_mask2)
            # Shuffle indices to get negative examples
            shuffled_indices = torch.randperm(b_ids2.size(0)).to(device)

            # Use shuffled indices to reorder both IDs and attention masks
            neg_ids = b_ids2[shuffled_indices]
            neg_mask = b_mask2[shuffled_indices]
            
            # Generate embeddings for negative examples
            negative_embed = model.forward(neg_ids, neg_mask)

            cos_sim_a = cosine_similarity_embedding(neutral_embed.unsqueeze(1), positive_embed.unsqueeze(0), temp = temp)
            cos_sim_b = cosine_similarity_embedding(neutral_embed.unsqueeze(1), negative_embed.unsqueeze(0), temp = temp)
            cos_sim = torch.cat([cos_sim_a, cos_sim_b], 1)
            loss_function = nn.CrossEntropyLoss()
            labels = torch.arange(cos_sim.size(0)).long().to(device)
            loss = loss_function(cos_sim,labels)
        else:
            if type == 'sts':
                logits = model.predict_similarity(b_ids1, b_mask1, b_ids2, b_mask2).to(device)
                loss = nn.MSELoss()(logits, b_labels.float().view(-1)) / args.batch_size
            else: # type == 'para'
                logits = model.predict_paraphrase(b_ids1, b_mask1, b_ids2, b_mask2).to(device)
                loss = nn.MSELoss()(logits.sigmoid(), b_labels.float().view(-1)) / args.batch_size

    return loss

## HELPER FUNCTION for train_multitask
def train_sst(sst_train_dataloader, sst_dev_dataloader, epoch, device, optimizer, model, unsupervised=False,supervised = False):
    sst_train_loss = 0
    sst_num_batches = 0
    for batch in tqdm(sst_train_dataloader, desc=f'train-{epoch}', disable=TQDM_DISABLE):
        optimizer.zero_grad()
        loss = calculate_loss(batch, device, model, 'sst', unsupervised,supervised)
        loss.backward()
        optimizer.step()

        sst_train_loss += loss.item()
        sst_num_batches += 1

    sst_train_loss = sst_train_loss / (sst_num_batches)
    sst_train_acc, train_f1, *_ = model_eval_sst(sst_train_dataloader, model, device)
    sst_dev_acc, dev_f1, *_ = model_eval_sst(sst_dev_dataloader, model, device)
    return sst_train_loss, sst_train_acc, sst_dev_acc

## HELPER FUNCTION for train_multitask
def train_sts(sts_train_dataloader, sts_dev_dataloader, epoch, device, optimizer, model, unsupervised=False,supervised = False):
    sts_train_loss = 0
    sts_num_batches = 0
    for batch in tqdm(sts_train_dataloader, desc=f'train-{epoch}', disable=TQDM_DISABLE):
        optimizer.zero_grad()
        loss = calculate_loss(batch, device, model, 'sts', unsupervised, supervised)
        loss.backward()
        optimizer.step()

        sts_train_loss += loss.item()
        sts_num_batches += 1

    sts_train_loss = sts_train_loss / (sts_num_batches)
    sts_train_acc = model_eval_sts(sts_train_dataloader, model, device)
    sts_dev_acc = model_eval_sts(sts_dev_dataloader, model, device)
    return sts_train_loss, sts_train_acc, sts_dev_acc

## HELPER FUNCTION for train_multitask
def train_para(para_train_dataloader, para_dev_dataloader, epoch, device, optimizer, model, unsupervised=False,supervised = False):
    train_loss = 0
    num_batches = 0
    for batch in tqdm(para_train_dataloader, desc=f'train-{epoch}', disable=TQDM_DISABLE):
        optimizer.zero_grad()
        loss = calculate_loss(batch, device, model, 'para', unsupervised,supervised)
        loss.backward()
        optimizer.step()

        train_loss += loss.item()
        num_batches += 1

    train_loss = train_loss / (num_batches)
    train_acc = model_eval_para(para_train_dataloader, model, device)
    dev_acc = model_eval_para(para_dev_dataloader, model, device)
    return train_loss, train_acc, dev_acc


# Batching from the three datasets at the same time (aka Concurrent Training)
# This function can perform gradient surgery and non-gradient surgery versions
def train_multiple(sst_train_dataloader, sst_dev_dataloader, 
                   sts_train_dataloader, sts_dev_dataloader, 
                   para_train_dataloader, para_dev_dataloader,
                   device, optimizer, model, do_grad_surgery, unsupervised,supervised):
    train_loss = 0
    num_batches = 0
    for i, (batch1, batch2, batch3) in enumerate(zip(sst_train_dataloader, sts_train_dataloader, para_train_dataloader)):
        optimizer.zero_grad()

        if do_grad_surgery:
            losses = [calculate_loss(batch1, device, model, 'sst', unsupervised,supervised), 
                      calculate_loss(batch2, device, model, 'sts', unsupervised,supervised),
                      calculate_loss(batch3, device, model, 'para', unsupervised,supervised)]
            loss = sum(losses)
            optimizer.pc_backward(losses) # using gradient surgery
            optimizer.step()  # apply gradient step
        else:
            loss = calculate_loss(batch1, device, model, 'sst', unsupervised,supervised) 
            loss += calculate_loss(batch2, device, model, 'sts', unsupervised,supervised) 
            loss += calculate_loss(batch3, device, model, 'para', unsupervised,supervised)
            loss.backward()
            optimizer.step()

        train_loss += loss.item()
        num_batches += 1
        if i % 100 == 0:
            print("100 batches processed")

    train_loss = train_loss / (num_batches)
    # evaluate the model
    sst_train_acc, train_f1, *_ = model_eval_sst(sst_train_dataloader, model, device)
    sst_dev_acc, dev_f1, *_ = model_eval_sst(sst_dev_dataloader, model, device)
    sts_train_acc = model_eval_sts(sts_train_dataloader, model, device)
    sts_dev_acc = model_eval_sts(sts_dev_dataloader, model, device)
    para_train_acc = model_eval_para(para_train_dataloader, model, device)
    para_dev_acc = model_eval_para(para_dev_dataloader, model, device)

    # calculate the combined accuracy
    dev_acc = sst_dev_acc + sts_dev_acc + para_dev_acc
    train_acc = sst_train_acc + sts_train_acc + para_train_acc
    return train_loss, train_acc, dev_acc


def train_multitask(args, load_model=False, unsupervised=False,supervised = False, epochs = 10):
    '''Train MultitaskBERT.

    Currently only trains on SST dataset. The way you incorporate training examples
    from other datasets into the training procedure is up to you. To begin, take a
    look at test_multitask below to see how you can use the custom torch `Dataset`s
    in datasets.py to load in examples from the Quora and SemEval datasets.
    '''
    device = torch.device('cuda') if args.use_gpu else torch.device('cpu')

    # Flag for whether to do Gradient Surgery or not
    do_grad_surgery = False
    # Flag for whether to do Sequential or Concurrent Training
    do_sequential = False

    # Create the data and its corresponding datasets and dataloaders
    sst_train_data, num_labels,para_train_data, sts_train_data = load_multitask_data(args.sst_train,args.para_train,args.sts_train, split ='train')
    sst_dev_data, num_labels,para_dev_data, sts_dev_data = load_multitask_data(args.sst_dev,args.para_dev,args.sts_dev, split ='train')

    # Truncate to make the same size
    if not do_sequential:
        min_len = min(len(sst_train_data), len(sts_train_data), len(para_train_data))
        sst_train_data = sst_train_data[:min_len]
        sts_train_data = sts_train_data[:min_len]
        para_train_data = para_train_data[:min_len]

    # Continue with dataloading
    sst_train_dataloader, sst_dev_dataloader = load_data(sst_train_data, sst_dev_data, args, 'sst')
    sts_train_dataloader, sts_dev_dataloader = load_data(sts_train_data, sts_dev_data, args, 'sts')
    para_train_dataloader, para_dev_dataloader = load_data(para_train_data, para_dev_data, args, 'para')

    # Init model.
    config = {'hidden_dropout_prob': args.hidden_dropout_prob,
              'num_labels': num_labels,
              'hidden_size': 768,
              'data_dir': '.',
              'option': args.option}

    if load_model:
        # Option 1: load in pretrained model
        saved = torch.load(args.filepath)
        config = saved['model_config']
        model = MultitaskBERT(config)
        model.load_state_dict(saved['model'])
        model = model.to(device)
        print(f"Pretrained model to train from {args.filepath}")
    else:
        # Option 2: build a new model
        config = SimpleNamespace(**config)
        model = MultitaskBERT(config)
        model = model.to(device)
        print("Built a new blank model")

    # Preparing for gradient surgery if applicable
    lr = args.lr
    if do_grad_surgery:
        optimizer = PCGrad(AdamW(model.parameters(), lr=lr)) 
    else:
        optimizer = AdamW(model.parameters(), lr=lr)
    best_dev_acc = 0

    # Run for the specified number of epochs.
    for epoch in range(epochs):
        model.train()

        # Training Sequential Version
        if do_sequential:
            sts_train_loss, sts_train_acc, sts_dev_acc = train_sts(sts_train_dataloader, sts_dev_dataloader, epoch, device, optimizer, model, unsupervised,supervised)
            sst_train_loss, sst_train_acc, sst_dev_acc = train_sst(sst_train_dataloader, sst_dev_dataloader, epoch, device, optimizer, model, unsupervised,supervised)
            para_train_loss, para_train_acc, para_dev_acc = train_para(para_train_dataloader, para_dev_dataloader, epoch, device, optimizer, model, unsupervised, supervised)

            # Combining the different tasks
            dev_acc = sst_dev_acc + sts_dev_acc + para_dev_acc
            train_acc = sst_train_acc + sts_train_acc + para_train_acc
            train_loss = sst_train_loss + sts_train_loss + para_train_loss

        # Training Concurrent Version
        else:
            train_loss, train_acc, dev_acc = train_multiple(sst_train_dataloader, sst_dev_dataloader, 
                                                            sts_train_dataloader, sts_dev_dataloader, 
                                                            para_train_dataloader, para_dev_dataloader,
                                                            device, optimizer, model, do_grad_surgery, unsupervised,supervised)

        if dev_acc > best_dev_acc:
            best_dev_acc = dev_acc
            save_model(model, optimizer, args, config, args.filepath) 

        print(f"Epoch {epoch}: Summed train loss :: {train_loss :.3f}, train acc :: {train_acc :.3f}, dev acc :: {dev_acc :.3f}")


def test_multitask(args):
    '''Test and save predictions on the dev and test sets of all three tasks.'''
    with torch.no_grad():
        device = torch.device('cuda') if args.use_gpu else torch.device('cpu')
        saved = torch.load(args.filepath)
        config = saved['model_config']

        model = MultitaskBERT(config)
        model.load_state_dict(saved['model'])
        model = model.to(device)
        print(f"Loaded model to test from {args.filepath}")

        sst_test_data, num_labels,para_test_data, sts_test_data = \
            load_multitask_data(args.sst_test,args.para_test, args.sts_test, split='test')

        sst_dev_data, num_labels,para_dev_data, sts_dev_data = \
            load_multitask_data(args.sst_dev,args.para_dev,args.sts_dev,split='dev')

        sst_test_data = SentenceClassificationTestDataset(sst_test_data, args)
        sst_dev_data = SentenceClassificationDataset(sst_dev_data, args)

        sst_test_dataloader = DataLoader(sst_test_data, shuffle=True, batch_size=args.batch_size,
                                         collate_fn=sst_test_data.collate_fn)
        sst_dev_dataloader = DataLoader(sst_dev_data, shuffle=False, batch_size=args.batch_size,
                                        collate_fn=sst_dev_data.collate_fn)

        para_test_data = SentencePairTestDataset(para_test_data, args)
        para_dev_data = SentencePairDataset(para_dev_data, args)

        para_test_dataloader = DataLoader(para_test_data, shuffle=True, batch_size=args.batch_size,
                                          collate_fn=para_test_data.collate_fn)
        para_dev_dataloader = DataLoader(para_dev_data, shuffle=False, batch_size=args.batch_size,
                                         collate_fn=para_dev_data.collate_fn)

        sts_test_data = SentencePairTestDataset(sts_test_data, args)
        sts_dev_data = SentencePairDataset(sts_dev_data, args, isRegression=True)

        sts_test_dataloader = DataLoader(sts_test_data, shuffle=True, batch_size=args.batch_size,
                                         collate_fn=sts_test_data.collate_fn)
        sts_dev_dataloader = DataLoader(sts_dev_data, shuffle=False, batch_size=args.batch_size,
                                        collate_fn=sts_dev_data.collate_fn)

        dev_sentiment_accuracy,dev_sst_y_pred, dev_sst_sent_ids, \
            dev_paraphrase_accuracy, dev_para_y_pred, dev_para_sent_ids, \
            dev_sts_corr, dev_sts_y_pred, dev_sts_sent_ids = model_eval_multitask(sst_dev_dataloader,
                                                                    para_dev_dataloader,
                                                                    sts_dev_dataloader, model, device)

        test_sst_y_pred, \
            test_sst_sent_ids, test_para_y_pred, test_para_sent_ids, test_sts_y_pred, test_sts_sent_ids = \
                model_eval_test_multitask(sst_test_dataloader,
                                          para_test_dataloader,
                                          sts_test_dataloader, model, device)

        with open(args.sst_dev_out, "w+") as f:
            print(f"dev sentiment acc :: {dev_sentiment_accuracy :.3f}")
            f.write(f"id \t Predicted_Sentiment \n")
            for p, s in zip(dev_sst_sent_ids, dev_sst_y_pred):
                f.write(f"{p} , {s} \n")

        with open(args.sst_test_out, "w+") as f:
            f.write(f"id \t Predicted_Sentiment \n")
            for p, s in zip(test_sst_sent_ids, test_sst_y_pred):
                f.write(f"{p} , {s} \n")

        with open(args.para_dev_out, "w+") as f:
            print(f"dev paraphrase acc :: {dev_paraphrase_accuracy :.3f}")
            f.write(f"id \t Predicted_Is_Paraphrase \n")
            for p, s in zip(dev_para_sent_ids, dev_para_y_pred):
                f.write(f"{p} , {s} \n")

        with open(args.para_test_out, "w+") as f:
            f.write(f"id \t Predicted_Is_Paraphrase \n")
            for p, s in zip(test_para_sent_ids, test_para_y_pred):
                f.write(f"{p} , {s} \n")

        with open(args.sts_dev_out, "w+") as f:
            print(f"dev sts corr :: {dev_sts_corr :.3f}")
            f.write(f"id \t Predicted_Similiary \n")
            for p, s in zip(dev_sts_sent_ids, dev_sts_y_pred):
                f.write(f"{p} , {s} \n")

        with open(args.sts_test_out, "w+") as f:
            f.write(f"id \t Predicted_Similiary \n")
            for p, s in zip(test_sts_sent_ids, test_sts_y_pred):
                f.write(f"{p} , {s} \n")


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sst_train", type=str, default="data/ids-sst-train.csv")
    parser.add_argument("--sst_dev", type=str, default="data/ids-sst-dev.csv")
    parser.add_argument("--sst_test", type=str, default="data/ids-sst-test-student.csv")

    parser.add_argument("--para_train", type=str, default="data/quora-train.csv")
    parser.add_argument("--para_dev", type=str, default="data/quora-dev.csv")
    parser.add_argument("--para_test", type=str, default="data/quora-test-student.csv")

    parser.add_argument("--sts_train", type=str, default="data/sts-train.csv")
    parser.add_argument("--sts_dev", type=str, default="data/sts-dev.csv")
    parser.add_argument("--sts_test", type=str, default="data/sts-test-student.csv")

    parser.add_argument("--seed", type=int, default=11711)
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--option", type=str,
                        help='pretrain: the BERT parameters are frozen; finetune: BERT parameters are updated',
                        choices=('pretrain', 'finetune'), default="pretrain")
    parser.add_argument("--use_gpu", action='store_true')

    parser.add_argument("--sst_dev_out", type=str, default="predictions/sst-dev-output.csv")
    parser.add_argument("--sst_test_out", type=str, default="predictions/sst-test-output.csv")

    parser.add_argument("--para_dev_out", type=str, default="predictions/para-dev-output.csv")
    parser.add_argument("--para_test_out", type=str, default="predictions/para-test-output.csv")

    parser.add_argument("--sts_dev_out", type=str, default="predictions/sts-dev-output.csv")
    parser.add_argument("--sts_test_out", type=str, default="predictions/sts-test-output.csv")

    parser.add_argument("--batch_size", help='sst: 64, cfimdb: 8 can fit a 12GB GPU', type=int, default=8)
    parser.add_argument("--hidden_dropout_prob", type=float, default=0.3)
    parser.add_argument("--lr", type=float, help="learning rate", default=1e-5)

    args = parser.parse_args()
    return args


if __name__ == "__main__":
    args = get_args()
    args.filepath = f'{args.option}-{args.epochs}-{args.lr}-multitask.pt' # Save path.
    seed_everything(args.seed)  # Fix the seed for reproducibility.

    do_contrastive = True # Flag for contrastive learning
    if do_contrastive:
        #print("hey! I'm doing supervised contrastive pretraining")
        #supervised contrastive learning         
        #train_multitask(args, load_model = False, epochs = 2, unsupervised = False, supervised = True)
        #unsupervised contrastive learning 
        print("hey! I am now doing unsupervised contrastive pretraining")
        train_multitask(args, load_model=False, epochs = args.epochs, unsupervised=True, supervised = False) 
    #multitask learning
    print("Hey! Now I am training on the task")
    train_multitask(args, load_model=True, epochs = args.epochs, unsupervised=False, supervised = False) 

    test_multitask(args)
