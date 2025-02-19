#!/usr/bin/env python3
# -*- coding: utf-8 -*-

###############################################################################
###############################################################################
###############################################################################
########    V1.0 2023/12/18     francescopiscitelli      ######################
###############################################################################
# automatically generated by the FlatBuffers compiler, do not modify

###############################################################################
###############################################################################

# import flatbuffers
# from flatbuffers.compat import import_numpy

import time
# import configargparse as argparse

# import matplotlib.pyplot as plt
import numpy as np
from confluent_kafka import Consumer, TopicPartition

# import os
import sys

from lib import libReadPcapngVMM as pcapr
from lib import libKafkaRX as krx 
from lib import libKafkaRawReadoutMessage as rawmsg
# 
# import libReadPcapngVMM as pcapr
# import libKafkaRX as krx 
# import libKafkaRawReadoutMessage as rawmsg

###############################################################################
###############################################################################

class  kafka_reader():
    def __init__(self, NSperClockTick, nOfPackets = 1, broker = '127.0.0.1:9092', topic = 'freia_debug', MONTTLtype = True , MONring = 11, timeResolutionType = 'fine', sortByTimeStampsONOFF = False, testing = False):
        
        self.readouts = pcapr.readouts()
                
        try:

            self.kaf = kafka_reader_preAlloc(NSperClockTick, nOfPackets, broker, topic, MONTTLtype, MONring, timeResolutionType,testing)
            self.kaf.allocateMemory()
            self.kaf.read()
            
            self.readouts = self.kaf.readouts
        
        except:
            
            print('\n... PRE-ALLOC method failed, exiting ...')
            
            sys.exit()
  
            
        finally:
             
              if sortByTimeStampsONOFF is True:
                 
                  print('Readouts are sorted by TimeStamp')
                 
                  self.readouts.sortByTimeStamps()
                 
            
              else:
                
                  print('Readouts are NOT sorted by TimeStamp')
                
              self.readouts.calculateDuration()   


class kafka_reader_preAlloc():
    def __init__(self, NSperClockTick, nOfPackets = 1, broker = '127.0.0.1:9092', topic = 'freia_debug', MONTTLtype = True , MONring = 11, timeResolutionType = 'fine',testing=False):
                
        self.NSperClockTick = NSperClockTick 
        self.nOfPackets     = nOfPackets
        self.broker         = broker 
        self.topic          = topic 
        self.MONTTLtype     = MONTTLtype
        self.MONring        = MONring
        self.timeResolutionType    = timeResolutionType

        #############################
        
        self.debug   = False
        
        self.testing = testing
        
        self.readouts = pcapr.readouts()
        
        self.rea = pcapr.pcapng_reader_PreAlloc(self.NSperClockTick,self.MONTTLtype,self.MONring,kafkaStream = True)
        
        #############################
        
        self.fileSize   = self.nOfPackets*(self.rea.singleReadoutSize*self.rea.readoutsPerPacket+self.rea.ESSheaderSize)
        print('streaming {} packets ({} kbytes) from kafka'.format(self.nOfPackets,self.fileSize/1000))
        
        #############################        
        
    def dprint(self, msg):
            if self.debug:
                print("{}".format(msg))
                
    def allocateMemory(self): 
        
        print('allocating memory',end='')
        
        numOfReadoutsTotal = self.nOfPackets*self.rea.readoutsPerPacket
        self.rea.counterCandidatePackets = self.nOfPackets
        self.rea.counterPackets          = self.nOfPackets
        self.preallocLength = round(numOfReadoutsTotal)
        self.dprint('preallocLength {}'.format(self.preallocLength))
        
        
    def read(self):   
            
        print('\n',end='')
        
        if self.testing is False:
        
            kafka_config = krx.generate_config(self.broker, True)
        
            consumer = Consumer(kafka_config)
            
            metadata = krx.get_metadata_blocking(consumer)
            if self.topic not in metadata.topics:
                raise Exception("Topic does not exist")
            
            topic_partitions = [TopicPartition(self.topic, p) for p in metadata.topics[self.topic].partitions]
            
            consumer.assign(topic_partitions)
                         
        self.rea.overallDataIndex = 0 
        self.rea.data             = np.zeros((self.preallocLength,15), dtype='int64') 
        
        self.rea.stepsForProgress = int(self.rea.counterCandidatePackets/4)+1  # 4 means 25%, 50%, 75% and 100%
        
        for npack in range(self.nOfPackets):

                    try:
                        
                        if self.testing is False:
                            while (msg := consumer.poll(timeout=0.5)) is None:
                                time.sleep(0.2)
                            
                            ar52 = rawmsg.RawReadoutMessage.GetRootAs(msg.value(), 0)
                            packetData   = ar52.RawDataAsNumpy().tobytes()
                            packetLength = len(packetData) 
                            
                        else:
                        
                        #  if you want generated data to test
                            bytesGens = bytesGen()
                            packetLength = bytesGens.packetLength
                            packetData   = bytesGens.packetData
                       
                        
                    except:
                        self.dprint('--> other packet found')
                            
                    else:
  
                        self.rea.extractFromBytes(packetData,packetLength)
                
  
        print('[100%]',end=' ') 

        self.dprint('\n All Packets {}, Candidates for Data {} --> Valid ESS {} (empty {}), NonESS  {} '.format(self.rea.counterPackets , self.rea.counterCandidatePackets,self.rea.counterValidESSpackets ,self.rea.counterEmptyESSpackets,self.rea.counterNonESSpackets))
           
          
        #######################################################       
             
        # here I remove  the rows that have been preallocated but no filled in case there were some packets big but no ESS
        if self.preallocLength > self.rea.totalReadoutCount:

            datanew = np.delete(self.rea.data,np.arange(self.rea.totalReadoutCount,self.preallocLength),axis=0)
            print('removing extra allocated length not used ...')
            
        elif self.preallocLength < self.rea.totalReadoutCount:
            print('something wrong with the preallocation: allocated length {}, total readouts {}'.format(self.preallocLength,self.rea.totalReadoutCount))
            sys.exit()
       
        elif self.preallocLength == self.rea.totalReadoutCount:
            
            datanew = self.rea.data
        
        cz = pcapr.checkIfDataHasZeros(datanew)
        datanew = cz.dataOUT
        
        self.readouts.transformInReadouts(datanew)
        

        # self.readouts.calculateTimeStamp(self.NSperClockTick)
        if self.timeResolutionType == 'fine':
            self.readouts.calculateTimeStampWithTDC(self.NSperClockTick)
        elif self.timeResolutionType == 'coarse':
            self.readouts.timeStamp = self.readouts.timeCoarse

        flag = self.readouts.checkIfCalibrationMode()
        
        if flag is True: 
            self.readouts.removeCalibrationData()
        
    
        print('\nkafka stream loaded - {} readouts - Packets: all {} (candidates {}) --> valid ESS {} (of which empty {}), nonESS {})'.format(self.rea.totalReadoutCount, self.rea.counterPackets,self.rea.counterCandidatePackets,self.rea.counterValidESSpackets ,self.rea.counterEmptyESSpackets,self.rea.counterNonESSpackets))    
        # print('\n')
        
class bytesGen():
    def __init__(self):
        
        # self.packetLength = 30+20*446
        # # self.packetData   = b"\x00\x00\x45\x53\x53\x72"+os.urandom(self.packetLength-6)
        
        # self.packetData   = b"\x00\x00\x45\x53\x53\x72"+bytearray([1] * self.packetLength-6)
        
        # dataPath='../data/'
        
        dataPath='./data/'
        
        # dataPath = '/Users/francescopiscitelli/Documents/PYTHON/MBUTYcap_develKafka/data/'
        
        with open(dataPath+'outputBinary1pkt', 'rb') as f: 
            temp =  self.packetData =  f.read()
           
        self.packetData =  temp[42:]
           
        self.packetLength = len(self.packetData)
        
        
        #  to write file from pcapr 
        # cont =+1 
        
        # if cont == 1 :
        #     # print(packetData)
        #     with open('/Users/francescopiscitelli/Documents/PYTHON/MBUTYcap_develKafka/lib/outputBin', 'wb') as f: 
        #         f.write(packetData)
                
        # else:
        #     with open('/Users/francescopiscitelli/Documents/PYTHON/MBUTYcap_develKafka/lib/outputBin', 'ab') as f: 
        #         f.write(packetData)
           
                
        # f.close()    
        
###############################################################################
###############################################################################

if __name__ == "__main__":
    
    NSperClockTick = 11.356860963629653  #ns per tick ESS for 88.0525 MHz
    
    aa = kafka_reader(NSperClockTick, nOfPackets = 1, testing=True)
    
    rr = aa.readouts
    
    rrarr = rr.concatenateReadoutsInArrayForDebug()
    
    
    # kaf = kafka_reader_preAlloc(NSperClockTick, nOfPackets=1)
    # kaf.allocateMemory()
    # kaf.read()
    
    
    
