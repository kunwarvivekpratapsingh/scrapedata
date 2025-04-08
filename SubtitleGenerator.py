import os
import json
import tempfile
from pathlib import Path
from typing import Any, Optional
import librosa
import soundfile as sf
import speech_recognition as sr
from langchain_openai import ChatOpenAI
from langchain.tools import BaseTool
from crewai import Agent, Task, Crew, Process

# Temp dir for intermediate files
temp_dir = tempfile.mkdtemp()


# === CUSTOM TOOL CLASSES ===
class AudioProcessingTool(BaseTool):
    name: str = "process_audio"
    description: str = "Enhance vocal clarity in the audio file."
    return_direct: bool = True

    def _run(self, input_file_path: str) -> str:
        try:
            y, sr_rate = librosa.load(input_file_path, sr=None)
            y_filtered = librosa.effects.preemphasis(y)
            y_harmonic, _ = librosa.effects.hpss(y_filtered)
            y_normalized = librosa.util.normalize(y_harmonic)
            processed_file = os.path.join(temp_dir, "processed_audio.wav")
            sf.write(processed_file, y_normalized, sr_rate)
            return processed_file
        except Exception as e:
            return f"Error processing audio: {str(e)}"

    async def _arun(self, input_file_path: str) -> str:
        return self._run(input_file_path)


class TranscriptionTool(BaseTool):
    name: str = "transcribe_audio"
    description: str = "Transcribe processed audio to text."
    return_direct: bool = True

    def _run(self, processed_file_path: str) -> str:
        recognizer = sr.Recognizer()
        y, sr_rate = librosa.load(processed_file_path, sr=None)
        duration = librosa.get_duration(y=y, sr=sr_rate)
        segment_length = 5
        segments = []
        for i in range(0, int(duration), segment_length):
            start_sample = int(i * sr_rate)
            end_sample = int(min((i + segment_length) * sr_rate, len(y)))
            segment = y[start_sample:end_sample]
            temp_seg_path = os.path.join(temp_dir, f"segment_{i}.wav")
            sf.write(temp_seg_path, segment, sr_rate)
            with sr.AudioFile(temp_seg_path) as source:
                audio = recognizer.record(source)
                try:
                    text = recognizer.recognize_google(audio)
                    if text:
                        segments.append({"start": i, "end": i + segment_length, "text": text})
                except:
                    pass
        json_path = os.path.join(temp_dir, "raw_transcription.json")
        with open(json_path, 'w') as f:
            json.dump(segments, f, indent=2)
        return json_path

    async def _arun(self, processed_file_path: str) -> str:
        return self._run(processed_file_path)


class SubtitleSyncTool(BaseTool):
    name: str = "synchronize_subtitles"
    description: str = "Align transcribed text with timestamps."
    return_direct: bool = True

    def _run(self, transcription_file: str) -> str:
        with open(transcription_file, 'r') as f:
            segments = json.load(f)
        refined = []
        for seg in segments:
            text = seg['text']
            duration = seg['end'] - seg['start']
            if len(text.split()) > 7 and duration > 3:
                words = text.split()
                chunk_size = 5
                chunks = [" ".join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]
                time_per_chunk = duration / len(chunks)
                for idx, chunk in enumerate(chunks):
                    refined.append({
                        "start": seg['start'] + idx * time_per_chunk,
                        "end": seg['start'] + (idx + 1) * time_per_chunk,
                        "text": chunk
                    })
            else:
                refined.append(seg)
        sync_path = os.path.join(temp_dir, "synced_subtitles.json")
        with open(sync_path, 'w') as f:
            json.dump(refined, f, indent=2)
        return sync_path

    async def _arun(self, transcription_file: str) -> str:
        return self._run(transcription_file)


class LyricsEnhancerTool(BaseTool):
    name: str = "enhance_lyrics"
    description: str = "Improve transcription for readability and format into SRT."
    return_direct: bool = True

    def _run(self, synced_file: str) -> str:
        with open(synced_file, 'r') as f:
            subtitles = json.load(f)
        enhanced = []
        for i, sub in enumerate(subtitles):
            context = ""
            if i > 0:
                context += f"Previous: {subtitles[i - 1]['text']}\n"
            context += f"Current: {sub['text']}\n"
            if i < len(subtitles) - 1:
                context += f"Next: {subtitles[i + 1]['text']}\n"
            enhanced_text = sub['text']  # For now, just using original text
            enhanced.append({"start": sub['start'], "end": sub['end'], "text": enhanced_text})

        def to_srt_time(sec):
            h, m, s = int(sec // 3600), int((sec % 3600) // 60), sec % 60
            ms = int((s - int(s)) * 1000)
            return f"{h:02}:{m:02}:{int(s):02},{ms:03}"

        srt_path = os.path.join(temp_dir, "enhanced_subtitles.srt")
        with open(srt_path, 'w') as f:
            for i, sub in enumerate(enhanced):
                f.write(f"{i + 1}\n{to_srt_time(sub['start'])} --> {to_srt_time(sub['end'])}\n{sub['text']}\n\n")
        return srt_path

    async def _arun(self, synced_file: str) -> str:
        return self._run(synced_file)


# === TOOL INSTANCES ===
process_audio_tool = AudioProcessingTool()
transcribe_audio_tool = TranscriptionTool()
synchronize_subtitles_tool = SubtitleSyncTool()
enhance_lyrics_tool = LyricsEnhancerTool()


# === AGENTS ===
def create_agents(llm):
    return [
        Agent(
            role="Audio Processing Specialist",
            goal="Enhance vocals in audio files",
            backstory="You are skilled in signal processing and can clean up noisy audio.",
            llm=llm,
            tools=[process_audio_tool],
            verbose=True
        ),
        Agent(
            role="Speech Recognition Expert",
            goal="Convert vocals into readable lyrics",
            backstory="You transcribe vocals into text accurately, even in noisy environments.",
            llm=llm,
            tools=[transcribe_audio_tool],
            verbose=True
        ),
        Agent(
            role="Timing Sync Specialist",
            goal="Align lyrics with correct timestamps",
            backstory="You are skilled at syncing spoken words with audio timeframes.",
            llm=llm,
            tools=[synchronize_subtitles_tool],
            verbose=True
        ),
        Agent(
            role="Lyrics Enhancer",
            goal="Polish and fix transcription errors",
            backstory="You refine lyrics for clarity and artistic quality.",
            llm=llm,
            tools=[enhance_lyrics_tool],
            verbose=True
        )
    ]


# === TASKS ===
def create_tasks(agents, music_file):
    return [
        Task(description=f"Process the audio at {music_file} to isolate vocals.", agent=agents[0]),
        Task(description="Transcribe the processed audio to text.", agent=agents[1]),
        Task(description="Sync the transcription with accurate timestamps.", agent=agents[2]),
        Task(description="Improve the transcription quality and format as SRT.", agent=agents[3])
    ]


# === MAIN EXECUTION ===
if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    music_file = r"D:\\CODING DEV\\BACKEND\\Python\\SubtitleGeneratorAgent\\MusicFile.mp3"
    llm = ChatOpenAI(model="gpt-4", temperature=0.7, api_key=os.getenv("OPENAI_API_KEY"))
    agents = create_agents(llm)
    tasks = create_tasks(agents, music_file)
    crew = Crew(agents=agents, tasks=tasks, process=Process.sequential, verbose=2)
    result = crew.kickoff()
    print("Subtitle generation complete. Output:", result)
