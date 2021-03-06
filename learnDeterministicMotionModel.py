import numpy as np
import torch
import torch.nn as nn
from torch.optim import Adam
from motionModel import deterministicMotionModel
from replayBuffer import ReplayBuffer
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import time
from ouNoise import ouNoise
from torch.utils.tensorboard import SummaryWriter
from standardizeData import standardizeData


class learnDeterministicMotionModel(object):
    def __init__(self,learningArgs,motionModelArgs):
        lr = learningArgs[0]
        lrDecay_stepSize = learningArgs[1]
        lrDecay_gamma = learningArgs[2]
        weight_decay = learningArgs[3]
        self.device = 'cuda:0' if torch.cuda.is_available() else 'cpu'
        self.MotionModel = deterministicMotionModel(motionModelArgs).to(self.device)
        self.optimizer = Adam(self.MotionModel.parameters(),lr = lr,weight_decay=weight_decay)
        self.lrScheduler = torch.optim.lr_scheduler.StepLR(self.optimizer, step_size=lrDecay_stepSize, gamma=lrDecay_gamma)
        self.criterion = torch.nn.MSELoss()
    def updateMotionModel(self,dataBatch):
        self.MotionModel.train()
        self.optimizer.zero_grad()
        actualNextStates = dataBatch[1][0]
        predictedNextStates = self.MotionModel(dataBatch[0])
        loss = self.criterion(actualNextStates,predictedNextStates)
        loss.backward()
        self.optimizer.step()
        self.lrScheduler.step()
        return loss.item()
    def evalMotionModel(self,dataBatch):
        self.MotionModel.eval()
        actualNextStates = dataBatch[1][0]
        predictedNextStates = self.MotionModel(dataBatch[0])
        loss = self.criterion(actualNextStates,predictedNextStates)
        return loss.item()

if __name__ == '__main__':
    # check if cuda available
    device = 'cuda:0' if torch.cuda.is_available() else 'cpu'
    writer = SummaryWriter()

    # load replay buffer
    cpuReplayBuffer = ReplayBuffer(loadDataPrefix='simData/',saveDataPrefix='simData/',chooseCPU = True)
    cpuReplayBuffer.loadData(matchLoadSize=True)
    outputDataSTD = standardizeData()
    outputDataSTD.getDistribution(cpuReplayBuffer.outputData[0])
    cpuReplayBuffer.outputData[0] = outputDataSTD.whiten(cpuReplayBuffer.outputData[0])

    data = cpuReplayBuffer.getRandBatch()
    inStateDim = data[0][0].shape[1]
    inMapDim = data[0][1].shape[2]
    inActionDim = data[0][2].shape[1]
    outStateDim = data[1][0].shape[1]

    # training/ neural network parameters
    learningRate = 0.01
    lrDecay_stepSize = 3000
    lrDecay_gamma = 0.9
    weight_decay=0
    learningArgs = [learningRate,lrDecay_stepSize,lrDecay_gamma,weight_decay]
    argDim = [inStateDim,inMapDim,inActionDim,outStateDim]
    convSizes = [[32,5],[32,4],[32,3]]
    fcSizes = [1024,512,256]#,128]
    networkSizes = [convSizes,fcSizes]
    dropout_ps = [0,0,0]
    motionModelArgs = [argDim,networkSizes,dropout_ps]
    Learn = learnDeterministicMotionModel(learningArgs,motionModelArgs)
    #Learn.MotionModel.load_state_dict(torch.load('randomTerrainMotionModel/motionModel.pt'))
    trainBatchSize = 128
    trainingSet = [0,0.8]
    testBatchSize = 512
    testSet = [trainingSet[1],1.0]

    numUpdates = 500000
    for updateCount in range(numUpdates):
        dataBatch = cpuReplayBuffer.getRandBatch(trainBatchSize,device=device,percentageRange=trainingSet)
        trainLoss = Learn.updateMotionModel(dataBatch)
        if updateCount%100==0:
            trainLoss = Learn.evalMotionModel(dataBatch)
            dataBatch = cpuReplayBuffer.getRandBatch(testBatchSize,device=device,percentageRange=testSet)
            testLoss = Learn.evalMotionModel(dataBatch)
            writer.add_scalar('train/mse_loss',trainLoss,updateCount)
            writer.add_scalar('test/mse_loss',testLoss,updateCount)
            writer.add_scalar('learning_rate',Learn.optimizer.state_dict()['param_groups'][-1]['lr'],updateCount)
            print("updateCount: " + str(updateCount) + " testLoss: " +str(testLoss) + " trainLoss: " + str(trainLoss) +  " lr: " + str(Learn.optimizer.state_dict()['param_groups'][-1]['lr']))
        if updateCount%50000==0:
            torch.save(Learn.MotionModel.state_dict(), 'motionModels/deterministic.pt')