#!/usr/bin/env python3
"""
   Voice activated audio recorder intended for scanner radio use
   Based on an original design by Kari Karvonen <oh1kk at toimii.fi>
   The original version had the following issues:
        1- There is a 2 second loss of data at the beginning of every recording.  This is due to the PyAudio stream being closed when
            an audio signal is detected and then reopened to start recording.
        2 -There is no voice recording while a file is being stored.  Example: if a recording is 3 minutes long, there is
           approximately 1.5 minutes that there is no detection of input signal while it processes the previous sound bite.
        3 - There is no protection from a long recording that uses up all available resources. It simply crashes the application.
    To address these deficientcies, the design has been modified with the following changes:
        1 - Implement multi-threading to handle the recording.  The recordings can be processed in parallel with a new voice is being buffered.
        2 - A long recording will be broken into segments to protect running out of system resources.  The default is to limit each recording to about 3.5 minutes.
        3 - the PyAudio stream is not closed, thus eliminating any data loss of voice beign recieved.
    V11.0 - Optimuized to record stream with no trimming.  Timeout after X seconds and breaks audio into chunks.
    v11.1 - Added Trim, and Add_Silence back in.
    v12.0 - switch from PyAudio to alsaaudio
    v12.1 - Added launching Pulseaudio as a deamon prior to running script. 
          - Tested running as a Supervisor service under user login of "pi".  See file /etc/supervisor/conf.d/vox.conf
                [program:vox]
                directory=/home/pi/tanner
                command=/home/pi/alsa/voxrecorder-alsa-12.py
                stopsignal=INT
                stopasgroup=true
                killasgroup=true
                user=pi
                autostart=true
                autorestart=true
                stderr_logfile=/var/log/vox.log
                stderr_logfile_maxbytes=10MB
                stdout_logfile=/var/log/vox.log
                stdout_logfile_maxbytes=10MB
    v13.0 - Added configuration printout.  (Tested for continious recording and passeed with shorter maximum length
"""

from __future__ import print_function
from sys import byteorder
from array import array
from struct import pack
from ctypes import * # required for Debug

import time
#import pyaudio
import wave
import os
import psutil
import alsaaudio # Added v12
import array     # added v12
import logging
import gc
#logging.basicConfig(format='%(threadName)s: %(asctime)s - %(name)s - %(message)s', level=logging.INFO)
logging.basicConfig(format='%(threadName)s: %(asctime)s - %(message)s', level=logging.INFO)

# MultiThreading
import threading
import numpy as np

# run pulse server
os.system("/usr/bin/pulseaudio -D");

DEBUGON = False
DEBUGMEM = False
VOXVERSION = 'v12.3'
#SILENCE_THRESHOLD = 4000
SILENCE_THRESHOLD = 2000
RECORD_AFTER_SILENCE_SECS = 5
MAX_CLIP_SIZE = 10000000 # 3Meg = aprox 1 minute
WAVEFILES_STORAGEPATH = os.path.expanduser("/mnt/ramdisk")

# PyAudio
#RATE = 44100
MAXIMUMVOL = 32767
#CHUNK_SIZE = 1024
#FORMAT = pyaudio.paInt16

# ALSA
CHANNELS    = 1
#INFORMAT    = alsaaudio.PCM_FORMAT_FLOAT_LE
INFORMAT    = alsaaudio.PCM_FORMAT_S16_LE
RATE        = 44100
FRAMESIZE   = 4096
SAMPLE_SIZE = 2 # Number of bytes per sample. (was a function in PyAudio)

def show_status(snd_data, record_started, record_started_stamp, wav_filename):
    "Displays volume levels"

    if voice_detected(snd_data, 'Show_status'):
        status = "Voice"
    else:
        status = "Silence"

    if record_started:
        elapsed = time.time() - record_started_stamp;
        #print('Recording to file', wav_filename, '-xx.wav Seconds:', elapsed)
    else:
        pass
	#print ('                                                                   ', end='')

def voice_detected(snd_data, snd_from):
    if not snd_data:
        logging.info('  --- sndData is NOT, from '+snd_from)
        return False
    else:
        #print(' -- max number', max(snd_data), ', Min = ', min(snd_data), ', Len = ', len(snd_data),'          ', end='\r')
        "Returns 'True' if sound peaked above the 'silent' threshold"
        #if (DEBUGON):
        #    logging.info(' -Debug: Max(snd_data)=[%s], Min(snd_data)=[%s]' % (max(snd_data),min(snd_data)))
        return max(snd_data) > SILENCE_THRESHOLD


def normalize(snd_data):
    "Average the volume out"
    times = float(MAXIMUMVOL)/max(abs(i) for i in snd_data)

    r = array.array('h')
    for i in snd_data:
        r.append(int(i*times))
    return r

def trim(snd_data):
    "Trim the blank spots at the start and end"
    def _trim(snd_data):
        record_started = False
        buffer_tr = array.array('h')

        for i in snd_data:
            if not record_started and abs(i)>SILENCE_THRESHOLD:
                record_started = True
                buffer_tr.append(i)

            elif record_started:
                buffer_tr.append(i)
        return buffer_tr

    # Trim to the left
    snd_data = _trim(snd_data)

    # Trim to the right
    snd_data.reverse()
    snd_data = _trim(snd_data)
    snd_data.reverse()
    return snd_data

def add_silence(snd_data, seconds):
    """Add silence to the start and end of 'snd_data' of length 'seconds' (float)"""
    buffer_si =array.array('h', [0 for i in range(int(seconds*RATE))])
    buffer_si.extend(snd_data)
    buffer_si.extend([0 for i in range(int(seconds*RATE))])
    return buffer_si

def memstat( strTemp):
    if (DEBUGMEM):
        mem =  psutil.virtual_memory()
        logging.info(' MEMORY (%s):' % ( strTemp))
        logging.info(f' - Available :{mem.available:13,}')
        logging.info(f' - percent   :{mem.percent:13,}')
        logging.info(f' - used      :{mem.used:13,}')
        logging.info(f' - free      :{mem.free:13,}')
        #logging.info(f' - active    :{mem.active:13,}')
        #logging.info(f' - inactive  :{mem.inactive:13,}')
        #logging.info(f' - buffers   :{mem.buffers:13,}')
        pass



def output_recording(sample_width, th_data, wav_filename):
    # Todo: copy array and populate.
    logging.info(' Begin Output Recording, '+ str(len(th_data)))
    #memstat('Before OR-1')
    data = array.array('h')
    data.extend(th_data)
    logging.info(' Finished duplicating data, '+ str(len(data)))

    del th_data
    memstat('In OR-2')

    #data = normalize(data)
    #logging.info(' finished normalize')
    data1 = trim(data)
    del data
    memstat('In OR-3')
    logging.info(' - finished trim')
    data2 = add_silence(data1, 0.5)
    del data1
    memstat('In OR-4')

    logging.info(' - finished add Silence')
    data3 = pack('<' + ('h'*len(data2)), *data2)
    del data2
    memstat('In OR-5')

    logging.info(' - begin of write file')

    wf = wave.open(wav_filename, 'wb')
    wf.setnchannels(1)
    wf.setsampwidth(sample_width)
    wf.setframerate(RATE)
    wf.writeframes(data3)
    wf.close()

    recinfo = ' - Recording finished. Saved to: %s' % (wav_filename)
    logging.info(recinfo)

    # Debug: Print memory useage
    memstat('End of Output Recording')
    
    del data3 # added to test freeing up the memory that is allocated.  What is best practice?
    del sample_width
    del wav_filename
    gc.collect()
    memstat('In OR, after del\'s.')

def record_audio():
    """
    Record audio when activity is detected
    Normalizes the audio, trims silence from the
    start and end, and pads with 0.5 seconds of
    blank sound to make sure VLC et al can play
    it without getting chopped off.
    """

    # Print out settings:
    logging.info('VOXVERSION = [%s]' % VOXVERSION)
    logging.info('SILENCE_THRESHOLD = [%s]' % SILENCE_THRESHOLD)
    logging.info('RECORD_AFTER_SILENCE_SECS = [%s]' % RECORD_AFTER_SILENCE_SECS)
    logging.info('MAX_CLIP_SIZE = [%s]' % MAX_CLIP_SIZE)
    logging.info('WAVEFILES_STORAGEPATH = [%s]' % WAVEFILES_STORAGEPATH)

    # Debug: Print memory useage
    memstat('Initial Program Launch')

    #p = pyaudio.PyAudio()
    #stream = p.open(format=FORMAT, channels=1, rate=RATE,
    #    input=True, output=True,
    #    frames_per_buffer=CHUNK_SIZE)
    #recorder=alsaaudio.PCM(type=alsaaudio.PCM_CAPTURE,channels=CHANNELS,rate=RATE,format=INFORMAT,periodsize=FRAMESIZE,device="hw:CARD=Device,DEV=0")
    recorder=alsaaudio.PCM(type=alsaaudio.PCM_CAPTURE,channels=CHANNELS,rate=RATE,format=INFORMAT,periodsize=FRAMESIZE,device="pulse")

    # loop forever while program is running.
    while True:
        record_started_stamp = 0
        last_voice_stamp = 0
        wav_filename = ''
        record_started = False
        max_reached = False #Added 05-12-2021 by PDSpencer

        #memstat('Before R')
        r = array.array('h')
        #memstat('After R')

        #snd_data = array.array('h')

        logging.info('- - - - Waiting for audio to be detected. - - - - -')
        while True: # Loop here until voice is detected
            """Loop until voice is detected """
            buffer = array.array('h')
            buffer.frombytes(recorder.read()[1])

            voice = voice_detected(buffer, 'silence') #"Returns 'True' if sound peaks above the 'silent' threshold"
            if ( DEBUGON):
                logging.info(' -<< Silence, voice=[%s], len(buffer)=[%s], max(buffer)=[%s]' % (voice,len(buffer),max(buffer)))

            if voice:
                last_voice_stamp = time.time()
                break

        # - Begin recording, audio has been detected
        logging.info('------------------------------------------------------------------------------')
        logging.info('begin of record audio')
        #memstat('Before R')
        r.extend(buffer) # Add current stream to data buffer
        #memstat('After R')


        while True: #Until Silence is detected
            buffer = array.array('h')
            buffer.frombytes(recorder.read()[1])

            r.extend(buffer)
            #logging.info('In AUDIO, len(buffer) = '+str(len(buffer)))

            voice = voice_detected(buffer, 'Audio')
            if ( DEBUGON):
                logging.info('->> Recording, voice=[%s], len(buffer)=[%s], max(buffer)=[%s], len(r)=[%s]' % (voice,len(buffer),max(buffer),len(r)))

            #logging.info(len(r))

            # -- Added a test here to close stream if reached maximum size  V10.0 05/10/2021
            if len(r) > MAX_CLIP_SIZE:
                voice = False
                max_reached = True
                logging.info('MAX-LENGTH-REACHED !! ---LEN(r)=[%s], wav_filename=[%s]' % (len(r),wav_filename))
                
            #show_status(buffer, record_started, record_started_stamp, wav_filename)

            if voice and record_started:
                last_voice_stamp = time.time();
            
            if voice and not record_started:
                record_started = True
                record_started_stamp = last_voice_stamp = time.time();
                datetime = time.strftime("%Y%m%d%H%M%S")
                wav_filename = '%s/voxrecord-%s-%s' % (WAVEFILES_STORAGEPATH,VOXVERSION,datetime)

            if record_started and time.time() > (last_voice_stamp + RECORD_AFTER_SILENCE_SECS):
                break

            if max_reached: # added 5/12/2021 by PDSpencer
                break

        # Start the recording process...
        datetime = time.strftime("%Y%m%d%H%M%S")
        logging.info('Break Stream.  Sending to recording....  -=-=-=-')
        wav_filename += '-%s.wav' % datetime

        th_data = array.array('h')
        th_data.extend(r)
        thread1 = threading.Thread(target=output_recording, args=(SAMPLE_SIZE, th_data, wav_filename))
        thread1.start()

        tmpstr = 'Thread Count = ' + str(threading.active_count())
        logging.info(tmpstr)

    return
    # - Should never reach here. Loops forever while program is running.

def voxrecord():
    """
    Listen for audio from soudcard. If audio is detected, record it to file. After recording,
    start again to wait for next activity
    """

    while True:
        logging.info('begin wait for activity')
        record_audio()

def py_error_handler(filename, line, function, err, fmt):
    pass

def py_supress_error():
    pass

def Xpy_supress_error():
    ERROR_HANDLER_FUNC = CFUNCTYPE(None, c_char_p, c_int, c_char_p, c_int, c_char_p)

    c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)

    asound = cdll.LoadLibrary('libasound.so')
    # Set error handler
    asound.snd_lib_error_set_handler(c_error_handler)

def vox_main():
    # Supress annoying ALSA error messages.
    py_supress_error()
    print("Voxrecorder started. Hit ctrl-c to quit.")

    if not os.access(WAVEFILES_STORAGEPATH, os.W_OK):
        print("Wave file save directory %s does not exist or is not writable. Aborting." % WAVEFILES_STORAGEPATH)
    else:
        voxrecord()

    print("Good bye.")

if __name__ == '__main__':
    # Main program is a function so that this program can be compiled if desired.
    vox_main()

