# -*- coding: utf-8 -*-
"""
author: Chris Hu
date: 2024/8/22
desc:
sample
"""

import json
import torch
import torch.nn as nn
import numpy as np
import random
import os

from torch.utils.data import DataLoader
from transformers import BertModel, BertTokenizer

"""
基于pytorch和bert的自回归语言训练模型
并用SFT训练问答模型
"""

Config = {
    "bert_path": "D:\\appdev\PyProject\Py_AI\第六周预训练模型\bert-base-chinese",
    "corpus_path": "./sample_data.json",
    "max_sequence_length": 100,
}

class LanguageModel(nn.Module):
    def __init__(self, vocab_size):
        super(LanguageModel, self).__init__()
        # self.embedding = nn.Embedding(len(vocab), input_dim)
        # self.layer = nn.LSTM(input_dim, input_dim, num_layers=1, batch_first=True)
        self.bert = BertModel.from_pretrained(Config["bert_path"], return_dict=False)
        input_dim = self.bert.config.hidden_size
        self.classify = nn.Linear(input_dim, vocab_size)
        # self.dropout = nn.Dropout(0.1)
        self.loss = torch.nn.CrossEntropyLoss(ignore_index=-1)

    # 当输入真实标签，返回loss值；无真实标签，返回预测值
    def forward(self, x, y=None, mask=None):
        if y is not None:
            x, _ = self.bert(x, attention_mask=mask)
            y_pred = self.classify(x)
            return self.loss(y_pred.view(-1, y_pred.shape[-1]), y.view(-1))
        else:
            x, _ = self.bert(x)
            y_pred = self.classify(x)
            return torch.softmax(y_pred, dim=-1)


# 加载语料
def load_corpus(path):
    title_list = []
    content_list = []
    with open(path, encoding="utf8") as f:
        for i, line in enumerate(f):
            line = json.loads(line)
            title_list.append(line["title"])
            content_list.append(line["content"])
    return [title_list, content_list]


# 建立数据集
# corpus  sample_data
def build_dataset(sample_length, tokenizer, corpus, max_len):
    dataset = []
    for i in range(sample_length):
        dataiter = build_sample(tokenizer, corpus, max_len)
        dataset.append(dataiter)
    return DataLoader(dataset, batch_size=32, shuffle=True, num_workers=0)


# 构建一个的mask
def create_mask(question_size, answer_size):
    len_s1 = question_size + 2  # cls + sep
    len_s2 = answer_size + 1  # sep
    # 创建掩码张量
    mask = torch.ones(len_s1 + len_s2, len_s1 + len_s2)
    # 遍历s1的每个token
    for i in range(len_s1):
        mask[i, len_s1:] = 0
    for i in range(len_s2):
        mask[len_s1 + i, len_s1 + i + 1:] = 0
    return mask


def pad_mask(tensor, target_shape):
    height, width = tensor.shape
    target_height, target_width = target_shape
    result = torch.zeros(target_shape, dtype=tensor.dtype, device=tensor.device)
    h_end = min(height, target_height)
    w_end = min(width, target_width)
    result[:h_end, :w_end] = tensor[:h_end, :w_end]
    return result


def build_sample(tokenizer, corpus, max_len):
    x_list, y_list = corpus
    random_index = random.randint(0, len(x_list) - 1)
    x = x_list[random_index]
    y = y_list[random_index]
    input_ids_x = tokenizer.encode(x, add_special_tokens=False)
    input_ids_y = tokenizer.encode(y, add_special_tokens=False)
    pad_x = [tokenizer.cls_token_id] + input_ids_x + [tokenizer.sep_token_id] + input_ids_y
    pad_y = len(input_ids_x) * [-1] + [-1] + input_ids_y
    pad_x = pad_x[:max_len] + [0] * (max_len - len(pad_x))
    pad_y = pad_y[:max_len] + [0] * (max_len - len(pad_y))

    mask = create_mask(len(input_ids_x), len(input_ids_y))
    mask = pad_mask(mask, (max_len, max_len))
    return [torch.LongTensor(pad_x), torch.LongTensor(pad_y), mask]


# 采样方式
def sampling_strategy(prob_distribution):
    if random.random() > 0.1:
        strategy = "greedy"
    else:
        strategy = "sampling"
    if strategy == "greedy":
        return int(torch.argmax(prob_distribution))
    elif strategy == "sampling":
        prob_distribution = prob_distribution.cpu().numpy()
        return np.random.choice(list(range(len(prob_distribution))), p=prob_distribution)


def evaluate(openings, model, tokenizer, max_sequence_length):
    model.eval()
    # 转化为input_id
    openings = tokenizer.encode(openings)
    # 控制生成的字数
    with torch.no_grad():
        while len(openings) <= max_sequence_length:
            x = torch.LongTensor([openings])
            if torch.cuda.is_available():
                x = x.cuda()
            # 因为有了mask 所以输入就是输出，看最后一个字的预测
            y_pred = model(x)[0][-1]
            index = sampling_strategy(y_pred)
            openings.append(index)
    return tokenizer.decode(openings)


def train(corpus_path, save_weights=True):
    num_epochs = 15  # 训练轮数
    # batch_size = 32  # 每次训练样本个数
    total_train_samples = 1000  # 每轮训练的样本总数
    max_sequence_length = Config["max_sequence_length"]  # 序列的最大长度
    learning_rate = 0.001  # 学习率

    # 加载词汇表和语料
    tokenizer = BertTokenizer.from_pretrained(Config["bert_path"])
    vocab_size = tokenizer.vocab_size
    corpus = load_corpus(corpus_path)

    # 构建模型
    model = LanguageModel(vocab_size)
    if torch.cuda.is_available():
        model = model.cuda()

    # 优化器
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)

    # 构建数据集
    dataset = build_dataset(total_train_samples, tokenizer, corpus, max_sequence_length)

    print("模型和数据集加载完毕，开始训练")

    # 训练循环
    for epoch in range(num_epochs):
        model.train()
        epoch_loss = []

        for x, y, mask in dataset:
            if torch.cuda.is_available():
                x, y, mask = x.cuda(), y.cuda(), mask.cuda()

            optimizer.zero_grad()  # 梯度归零
            loss = model(x, y, mask)  # 计算损失
            loss.backward()  # 反向传播
            optimizer.step()  # 更新权重
            epoch_loss.append(loss.item())

        average_loss = np.mean(epoch_loss)
        print(f"=========\n第 {epoch + 1} 轮平均损失: {average_loss:.6f}")

        # 评估模型
        sample_sentence = "黑神话上线，有许多其他国家玩家喜欢"
        evaluation_result = evaluate(sample_sentence, model, tokenizer, max_sequence_length)
        print(evaluation_result)

    # 保存模型权重
    if save_weights:
        model_filename = os.path.basename(corpus_path).replace(".txt", ".pth")
        model_save_path = os.path.join("model", model_filename)
        torch.save(model.state_dict(), model_save_path)


if __name__ == "__main__":
    train("sample_data.json", save_weights=False)