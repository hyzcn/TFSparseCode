import pdb
import numpy as np
import tensorflow as tf
from base import base
from plots.plotWeights import plot_weights
from plots.plotRecon import plotRecon
from .utils import *
#Using pvp files for saving
from pvtools import *

class LCA_ADAM(base):
    #Sets dictionary of params to member variables
    def loadParams(self, params):
        super(LCA_ADAM, self).loadParams(params)
        self.learningRateA = params['learningRateA']
        self.learningRateW = params['learningRateW']
        self.thresh = params['thresh']
        self.numV = params['numV']
        self.VStrideY = params['VStrideY']
        self.VStrideX = params['VStrideX']
        self.patchSizeY = params['patchSizeY']
        self.patchSizeX = params['patchSizeX']

    def runModel(self):
        #Normalize weights to start
        self.normWeights()

        #Training
        for i in range(self.numIterations):
           if(i%self.savePeriod == 0):
               self.trainA(True)
           else:
               self.trainA(False)
           #Train
           self.trainW()
           self.normWeights()

    #Constructor takes inputShape, which is a 3 tuple (ny, nx, nf) based on the size of the image being fed in
    def __init__(self, params, dataObj):
        super(LCA_ADAM, self).__init__(params, dataObj)
        data = self.dataObj.getData(self.batchSize)
        self.currImg = data[0]
        #TODO set ground truth

    #Builds the model. inMatFilename should be the vgg file
    def buildModel(self, inputShape):
        #inputShape goes (y, x, f)
        assert(inputShape[0] % self.VStrideY == 0)
        assert(inputShape[1] % self.VStrideX == 0)
        V_Y = int(inputShape[0]/self.VStrideY)
        V_X = int(inputShape[1]/self.VStrideX)
        self.imageShape = (self.batchSize, inputShape[0], inputShape[1], inputShape[2])
        self.WShape = (self.patchSizeY, self.patchSizeX, 3, self.numV)
        self.VShape = (self.batchSize, V_Y, V_X, self.numV)

        #Running on GPU
        with tf.device(self.device):
            with tf.name_scope("inputOps"):
                #Get convolution variables as placeholders
                self.inputImage = node_variable(self.imageShape, "inputImage")
                #Scale inputImage
                self.scaled_inputImage = self.inputImage/np.sqrt(self.patchSizeX*self.patchSizeY*inputShape[2])

            with tf.name_scope("Dictionary"):
                self.V1_W = sparse_weight_variable(self.WShape, "V1_W")

            with tf.name_scope("weightNorm"):
                self.normVals = tf.sqrt(tf.reduce_sum(tf.square(self.V1_W), reduction_indices=[0, 1, 2], keep_dims=True))
                self.normalize_W = self.V1_W.assign(self.V1_W/(self.normVals + 1e-8))

            with tf.name_scope("LCA_ADAM"):
                self.V1_U = uniform_weight_variable(self.VShape, "V1_U", 0.0, 1.25*self.thresh)
                self.V1_A = weight_variable(self.VShape, "V1_A", 1e-3)

            with tf.name_scope("Recon"):
                assert(self.VStrideY >= 1)
                assert(self.VStrideX >= 1)
                #We build index tensor in numpy to gather
                self.recon = conv2d_oneToMany(self.V1_A, self.V1_W, self.imageShape, "recon", self.VStrideY, self.VStrideX)

            with tf.name_scope("Error"):
                self.error = self.scaled_inputImage - self.recon

            with tf.name_scope("Loss"):
                self.reconError = tf.reduce_mean(tf.reduce_sum(tf.square(self.error), reduction_indices=[1, 2, 3]))
                self.l1Sparsity = tf.reduce_mean(tf.reduce_sum(tf.abs(self.V1_A), reduction_indices=[1, 2, 3]))
                #self.reconError = tf.reduce_mean(tf.square(self.error))
                #self.l1Sparsity = tf.reduce_mean(tf.abs(self.V1_A))
                #Define loss
                self.loss = self.reconError/2 + self.thresh * self.l1Sparsity

            with tf.name_scope("Opt"):
                #Calculate A from U
                self.optimizerA0 = self.V1_A.assign(tf.nn.relu(self.V1_U - self.thresh))

                self.optimizerA1 = tf.train.AdamOptimizer(self.learningRateA)

                #Find gradient wrt A
                self.lossGrad = self.optimizerA1.compute_gradients(self.reconError, [self.V1_A])
                #Apply such gradient to U
                self.dU = [(self.lossGrad[0][0] - self.V1_A + self.V1_U, self.V1_U)];

                self.optimizerA = self.optimizerA1.apply_gradients(self.dU)

                self.optimizerW = tf.train.AdadeltaOptimizer(self.learningRateW, epsilon=1e-6).minimize(self.loss,
                        var_list=[
                            self.V1_W
                        ])

            with tf.name_scope("stats"):
                self.nnz = tf.reduce_mean(tf.cast(tf.not_equal(self.V1_A, 0), tf.float32))

                self.errorStd = tf.sqrt(tf.reduce_mean(tf.square(self.error-tf.reduce_mean(self.error))))*np.sqrt(self.patchSizeY*self.patchSizeX*inputShape[2])
                self.l1_mean = tf.reduce_mean(tf.abs(self.V1_A))

                self.weightImages = tf.transpose(self.V1_W, [3, 0, 1, 2])

                #For log of activities
                self.log_V1_A = tf.log(tf.abs(self.V1_A)+1e-15)

        #Summaries
        self.s_loss = tf.summary.scalar('loss', self.loss)
        self.s_recon = tf.summary.scalar('recon error', self.reconError)
        self.s_errorStd= tf.summary.scalar('errorStd', self.errorStd)
        self.s_l1= tf.summary.scalar('l1 sparsity', self.l1Sparsity)
        self.s_l1_mean = tf.summary.scalar('l1 mean', self.l1_mean)
        self.s_s_nnz = tf.summary.scalar('nnz', self.nnz)

        self.h_input = tf.summary.histogram('input', self.inputImage)
        self.h_recon = tf.summary.histogram('recon', self.recon)
        self.h_v1_w = tf.summary.histogram('V1_W', self.V1_W)

        self.h_v1_u = tf.summary.histogram('V1_U', self.V1_U)
        self.h_v1_a = tf.summary.histogram('V1_A', self.V1_A)
        self.h_log_v1_a = tf.summary.histogram('Log_V1_A', self.log_V1_A)

        self.h_normVals = tf.summary.histogram('normVals', self.normVals)


    def encodeImage(self, feedDict):
        for i in range(self.displayPeriod):
            #Run optimizer
            #This calculates A
            self.sess.run(self.optimizerA0, feed_dict=feedDict)
            #This updates U based on loss function wrt A
            self.sess.run(self.optimizerA, feed_dict=feedDict)
            self.timestep+=1
            if((i+1)%self.writeStep == 0):
                summary = self.sess.run(self.mergedSummary, feed_dict=feedDict)
                self.train_writer.add_summary(summary, self.timestep)
            if((i+1)%self.progress == 0):
                print "Timestep ", self.timestep

    #Trains model for numSteps
    def trainA(self, save):
        #Define session
        feedDict = {self.inputImage: self.currImg}
        self.encodeImage(feedDict)

        if(save):
            save_path = self.saver.save(self.sess, self.saveFile, global_step=self.timestep, write_meta_graph=False)
            print("Model saved in file: %s" % save_path)
            #Print weights
            self.writeNpWeights(self.ckptDir + "weights_" + str(self.timestep))


    def normWeights(self):
        #Normalize weights
        self.sess.run(self.normalize_W)

    def trainW(self):
        feedDict = {self.inputImage: self.currImg}

        #Visualization
        if (self.plotTimestep % self.plotPeriod == 0):
            np_V1_W = self.sess.run(self.weightImages)
            np_v1 = self.sess.run(self.V1_A, feed_dict=feedDict)
            plot_weights(np_V1_W, self.plotDir+"dict_"+str(self.timestep)+".png", v1Rank=np_v1)
            #Draw recons
            np_inputImage = self.currImg
            np_recon = self.sess.run(self.recon, feed_dict=feedDict)
            plotRecon(np_recon, np_inputImage, self.plotDir+"recon_"+str(self.timestep), r=range(4))

        #Update weights
        self.sess.run(self.optimizerW, feed_dict=feedDict)
        #New image
        self.currImg = self.dataObj.getData(self.batchSize)[0]
        self.plotTimestep += 1

    def getLoadVars(self):
        v = tf.global_variables()
        v = [var for var in v if ("Adam" not in var.name and "Adadelta" not in var.name)]
        return v

    #Finds sparse encoding of inData
    #inData must be in the shape of the image
    #[batch, nY, nX, nF]
    def evalData(self, inData):
        (nb, ny, nx, nf) = inData.shape
        #Check size
        assert(nb == self.batchSize)
        assert(ny == self.inputShape[0])
        assert(nx == self.inputShape[1])
        assert(nf == self.inputShape[2])

        feedDict = {self.inputImage: inData}
        self.encodeImage(feedDict)
        #Get thresholded v1 as an output
        outVals = self.V1_A.eval(session=self.sess)
        return outVals

    def evalSet(self, evalDataObj, outFilename):
        numImages = evalDataObj.numImages
        #skip must be 1 for now
        assert(evalDataObj.skip == 1)
        numIterations = int(np.ceil(float(numImages)/self.batchSize))

        pvFile = pvpOpen(outFilename, 'w')
        for it in range(numIterations):
            print str((float(it)*100)/numIterations) + "% done (" + str(it) + " out of " + str(numIterations) + ")"
            #Evaluate
            npV1_A = self.evalData(self.currImg)
            v1Sparse = convertToSparse4d(npV1_A)
            time = range(it*self.batchSize, (it+1)*self.batchSize)
            data = {"values":v1Sparse, "time":time}
            pvFile.write(data, shape=(self.VShape[1], self.VShape[2], self.VShape[3]))
            self.currImg = self.dataObj.getData(self.batchSize)
        pvFile.close()

    def writeNpWeights(self, outputPrefix):
        npw = self.sess.run(self.V1_W)
        filename = outputPrefix + ".npy"
        np.save(filename, npw)


