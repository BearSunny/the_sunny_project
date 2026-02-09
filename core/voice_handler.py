"""
Voice Handler for Sunny Research Assistant
Voice Input: speech_recognition (Windows native speech API)
Voice Output: gtts (Google Text-to-Speech) + pygame.mixer for direct playback
"""

import threading
import time
import os

from typing import Callable, Optional
from dotenv import load_dotenv
import google.generativeai as genai


load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


class VoiceHandler:
    """
    Handles voice input/output.
    STT: speech_recognition (Windows native API, no ML models needed)
    TTS: gtts (Google Text-to-Speech) + pygame.mixer for simple direct playback
    """
    
    def __init__(self, on_user_speech: Callable[[str], None]):
        """
        Initialize voice handler
        
        Args:
            on_user_speech: Callback function when user speech is detected
        """
        self.on_user_speech = on_user_speech
        self.is_running = False
        self.is_speaking = False  # Flag to pause input while speaking
        self.recognizer = None
        self.microphone = None
        
        # Check dependencies
        try:
            import gtts
            import pygame
            pygame.mixer.init()
            print("Voice handler initialized (speech_recognition + gtts + pygame.mixer)")
        except ImportError as e:
            print(f"Warning: TTS dependencies missing: {e}")
            print("Install with: pip install gtts pygame")

    def start_listening(self):
        """Start listening for voice input"""
        self.is_running = True
        print("Initializing voice input...\n")
        
        # Try to capture from microphone first
        microphone_available = False
        
        try:
            import speech_recognition as sr
            self.recognizer = sr.Recognizer()
            self.microphone = sr.Microphone()
            
            print("  Testing microphone...")
            with self.microphone as source:
                # Adjust noise level
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
            
            print("Microphone initialized successfully")
            
            # Start listening thread
            threading.Thread(target=self._listen_for_speech, daemon=True).start()
            microphone_available = True
            
        except ImportError:
            print(f"speech_recognition not installed")
            print("    Install with: pip install SpeechRecognition")
        except OSError as e:
            print(f"Microphone device not found: {e}")
            print("    Make sure a microphone is connected")
        except Exception as e:
            print(f"Microphone initialization failed: {type(e).__name__}: {e}")
        
        # Fallback to keyboard input if microphone isn't available
        if not microphone_available:
            print("\n" + "=" * 60)
            print("KEYBOARD MODE: Type commands instead of speaking")
            print("=" * 60)
            print("Examples:")
            print("  Hey Sunny, what's this paper about?")
            print("  Hey Sunny, analyze the methodology")
            print("=" * 60 + "\n")
            threading.Thread(target=self._keyboard_input_fallback, daemon=True).start()

    def _listen_for_speech(self):
        """Listen for speech input and transcribe"""
        import speech_recognition as sr
        
        print("(Ready for voice input - say 'Hey Sunny')\n")
        
        while self.is_running:
            # Skip listening while Sunny is speaking (prevents feedback loop)
            if self.is_speaking:
                time.sleep(0.1)
                continue
            
            try:
                with self.microphone as source:
                    # Listen with timeout
                    audio = self.recognizer.listen(source, timeout=1.0, phrase_time_limit=10)
                
                # Transcribe using Google Speech Recognition (free, no key needed)
                try:
                    text = self.recognizer.recognize_google(audio)
                    if text and len(text.strip()) > 0:
                        print(f"You: {text}")
                        self.on_user_speech(text.strip())
                except sr.UnknownValueError:
                    # Silently continue, user wasn't understood
                    pass
                except sr.RequestError:
                    # Google API unavailable, just continue
                    pass
                    
            except sr.WaitTimeoutError:
                # No speech detected in timeout period, continue listening
                pass
            except Exception as e:
                # Log but continue
                pass

    def _keyboard_input_fallback(self):
        """
        Fallback to keyboard input when microphone is unavailable.
        Reads user input from stdin instead of voice.
        """
        print("\n(Ready for keyboard input)\n")
        while self.is_running:
            try:
                text = input("You: ").strip()
                if text:
                    self.on_user_speech(text)
            except EOFError:
                break
            except Exception as e:
                pass

    def speak(self, text: str):
        """
        Text to speech using gtts + pygame.mixer.
        Speaks asynchronously without blocking, pausing voice input while speaking.
        """
        print(f"Sunny: {text}")
        
        # Run TTS in background thread to avoid blocking
        threading.Thread(target=self._speak_async, args=(text,), daemon=True).start()
    
    def _speak_async(self, text: str):
        """
        Async TTS using gtts + pygame.mixer.
        Generates speech from text and plays it directly.
        Pauses voice input during playback to prevent feedback loops.
        """
        try:
            from gtts import gTTS
            import pygame
            import tempfile
            
            # Set flag to pause voice input while speaking
            self.is_speaking = True
            
            # Generate speech using gTTS (Google Text-to-Speech)
            tts = gTTS(text=text, lang='en', slow=False)
            
            # Save temporarily
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp:
                tts.save(tmp.name)
                tmp_path = tmp.name
            
            # Play the audio using pygame.mixer
            pygame.mixer.music.load(tmp_path)
            pygame.mixer.music.play()
            
            # Wait for playback to finish
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
            
            # Wait a bit for pygame to fully release the file handle on Windows
            time.sleep(0.2)
            
            # Clean up - retry on Windows file lock errors
            try:
                os.unlink(tmp_path)
            except OSError:
                time.sleep(0.5)
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass  # File might be in use, will be cleaned by OS
            
            # Resume voice input after speaking
            self.is_speaking = False
            
        except ImportError as e:
            print(f"[TTS Error] Missing dependency: {e}")
            self.is_speaking = False
        except Exception as e:
            print(f"[TTS Error] {type(e).__name__}: {e}")
            self.is_speaking = False
    
    def stop(self):
        """Stop voice handler"""
        self.is_running = False
        print("Voice handler stopped")

def create_voice_handler(on_user_speech: Callable[[str], None], 
                        use_live_api: bool = True) -> VoiceHandler:
    return VoiceHandler(on_user_speech)
