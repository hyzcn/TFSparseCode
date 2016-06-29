#import matplotlib
#matplotlib.use('Agg')
from dataObj.image import tfObj
from tf.slp_sparse_code import SLP
import numpy as np
import pdb

#Paths to list of filenames
trainFileList = "/home/slundquist/mountData/tfLCA/cifar_eval/train.txt"
trainGtList =  "/home/slundquist/mountData/datasets/cifar/images/train.txt"

testFileList = "/home/slundquist/mountData/tfLCA/cifar_eval/test.txt"
testGtList =  "/home/slundquist/mountData/datasets/cifar/images/test.txt"

#Get object from which tensorflow will pull data from
trainDataObj = tfObj(trainFileList, trainGtList, (16, 16, 128), resizeMethod="crop", shuffle=False, skip=1, seed=None)
testDataObj = tfObj(testFileList, testGtList, (16, 16, 128), resizeMethod="crop", shuffle=False, skip=1, seed=None)

params = {
    #Base output directory
    'outDir':          "/home/slundquist/mountData/DeepGAP/",
    #Inner run directory
    'runDir':          "/cifar/",
    'tfDir':           "/tfout",
    #Save parameters
    'ckptDir':         "/checkpoints/",
    'saveFile':        "/save-model",
    'savePeriod':      100, #In terms of displayPeriod
    #output plots directory
    'plotDir':         "plots/",
    'plotPeriod':      100, #With respect to displayPeriod
    #Progress step
    'progress':        10,
    #Controls how often to write out to tensorboard
    'writeStep':       100, #300,
    #Flag for loading weights from checkpoint
    'load':            False,
    'loadFile':        "/home/slundquist/mountData/DeepGAP/saved/cifar.ckpt",
    #Input vgg file for preloaded weights
    'pvpWeightFile':   "/home/slundquist/mountData/tfLCA/cifar_train/pvp/ista.pvp",
    #Device to run on
    'device':          '/gpu:0',
    #Num iterations
    'outerSteps':      1000, #1000000,
    'innerSteps':      50, #300,
    #Batch size
    'batchSize':       32,
    #Learning rate for optimizer
    'learningRate':    1e-5,
    'numClasses':      10,

    #####ISTA PARAMS######
    'VStrideY':        2,
    'VStrideX':        2,
}

#Allocate tensorflow object
#This will build the graph
tfObj = SLP(params, trainDataObj.inputShape)

print "Done init"
tfObj.runModel(trainDataObj, testDataObj = testDataObj)
print "Done run"

tfObj.closeSess()

