# vox-recorder

Voice activated audio recorder intended for scanner radio or any audio input that has long periods of silence. Recording starts when the audio level is higher than a defined threshold and recording ends after 5 seconds of silence.

## Depencies
python3
python3-pyaudio

## Usage

./vox-recorder.py

Audio recordings will be saved to a defined directory. The file type is wav. Audio file names are timestamped eg,

    voxrecord-20180705222631-20180705222639.wav
    
Uses pulseaudio so that the Python program can multitask both recieving audio and creating output files concurrently.

## Licence

GPLv3
