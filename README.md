# vox-recorder

Voice activated audio recorder intended for scanner radio or any audio input that has long periods of silence. Recording starts when the audio level is higher than a defined threshold and recording ends after 5 seconds of silence.

## Dependancies
python3
python3-pulseaudio
psutils

## Usage

./vox-recorder-xx.py

Audio recordings will be saved to a defined directory. The file type is wav. Audio file names are timestamped eg,

    voxrecord-20180705222631-20180705222639.wav
    
Uses pulseaudio so that the Python program can multitask both recieving audio and creating output files concurrently.

## High level program logic
The program does the following: 
 - Initializes Pulse Audio input.
 - loops reading a 4k buffer of audio input
   - Looks for a maximum signal in the 4k buffer that is about the threshhold (default 2000)
   - If it detects any valid audio, exit the "While Silence" loop and enter a "Record while sound" loop.
 - Loops looking for a 5 seconds of silence or maximum length.  Both trigger it to start the "Store Recieved Data" event.
 - When a "Store recieved Data" event is encountered, it launches a thread to process the input data.

The "Store Revieved Data" does the following:
  1. trims any silence from the beginning and end of the recording
  2. Optionally normalizes the data.  If the maximum volume is less that the maximum (32767) then adjust the volume to be louder.
  3. Add a half second silence to the beginning and end of the audio.
  4. Store the audio file with the name indicating the start date and stop date (detailed to the second) 
 
 Note: I have used an external cron job keep the file directory from filling up.   
## Licence

GPLv3
