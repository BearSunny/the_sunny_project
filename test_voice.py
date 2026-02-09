#!/usr/bin/env python3
"""
Test script for voice input/output using speech_recognition and gtts + pygame.mixer.
This validates that both STT (Speech-to-Text) and TTS (Text-to-Speech) work correctly.
"""

import sys
import time
import speech_recognition as sr


def test_tts():
    """Test text-to-speech using gtts + pygame.mixer."""
    print("\n=== Testing TTS (Text-to-Speech) ===")
    try:
        from gtts import gTTS
        import pygame
        import tempfile
        import os
        
        # Initialize pygame mixer
        pygame.mixer.init()
        
        test_phrases = [
            "Hello, this is a test of the Google Text to Speech system.",
            "The voice input and output system is now working.",
            "Welcome to Sunny, your AI research assistant."
        ]
        
        for phrase in test_phrases:
            print(f"Speaking: {phrase}")
            
            # Generate speech using gTTS
            tts = gTTS(text=phrase, lang='en', slow=False)
            
            # Save to temp file
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp:
                tts.save(tmp.name)
                tmp_path = tmp.name
            
            # Play the audio
            pygame.mixer.music.load(tmp_path)
            pygame.mixer.music.play()
            
            # Wait for playback to finish
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
            
            # Wait a bit for pygame to fully release file handle on Windows
            time.sleep(0.2)
            
            # Clean up - retry on Windows file lock errors
            try:
                os.unlink(tmp_path)
            except OSError:
                time.sleep(0.5)
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            
            time.sleep(0.5)
        
        print("[PASS] TTS test passed - all phrases spoken successfully")
        return True
    except Exception as e:
        print(f"[FAIL] TTS test failed: {e}")
        return False


def test_stt():
    """Test speech-to-text using speech_recognition."""
    print("\n=== Testing STT (Speech-to-Text) ===")
    try:
        recognizer = sr.Recognizer()
        microphone = sr.Microphone()
        
        # Adjust for ambient noise
        print("Adjusting for ambient noise (listening for 2 seconds)...")
        with microphone as source:
            recognizer.adjust_for_ambient_noise(source, duration=2)
        
        print("[OK] Microphone and noise adjustment initialized")
        print("\nListening for speech... (say something within 10 seconds)")
        
        with microphone as source:
            try:
                audio = recognizer.listen(source, timeout=10, phrase_time_limit=10)
                print("Audio captured, processing...")
                
                # Try Google Speech Recognition
                text = recognizer.recognize_google(audio)
                print(f"[OK] Recognized speech: '{text}'")
                return True
            except sr.UnknownValueError:
                print("[FAIL] Could not understand audio")
                return False
            except sr.RequestError as e:
                print(f"[FAIL] Could not request results: {e}")
                return False
    except OSError:
        print("[WARN] No microphone detected - falling back to keyboard input")
        print("To test STT properly, ensure your system has a working microphone.")
        return None
    except Exception as e:
        print(f"[FAIL] STT test failed: {e}")
        return False


def test_keyboard_fallback():
    """Test keyboard input as fallback."""
    print("\n=== Testing Keyboard Fallback ===")
    try:
        print("Enter a test message (or press Ctrl+C to skip):")
        user_input = input("> ")
        print(f"Received: '{user_input}'")
        print("[OK] Keyboard fallback works")
        return True
    except KeyboardInterrupt:
        print("\n(Skipped keyboard test)")
        return None
    except Exception as e:
        print(f"[FAIL] Keyboard test failed: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 50)
    print("Voice System Integration Test")
    print("Testing: speech_recognition + gtts + pygame.mixer")
    print("=" * 50)
    
    results = {}
    
    # Test TTS first (doesn't require user input)
    results['TTS (gtts+pygame)'] = test_tts()
    
    # Test STT with microphone
    results['STT (speech_recognition)'] = test_stt()
    
    # Test keyboard fallback
    results['Keyboard Fallback'] = test_keyboard_fallback()
    
    # Summary
    print("\n" + "=" * 50)
    print("Test Summary")
    print("=" * 50)
    for test_name, result in results.items():
        if result is None:
            status = "SKIPPED"
        elif result:
            status = "PASSED"
        else:
            status = "FAILED"
        print(f"{test_name}: {status}")
    
    # Overall result
    passed = sum(1 for r in results.values() if r is True)
    total = len([r for r in results.values() if r is not None])
    print(f"\nOverall: {passed}/{total} tests passed")

if __name__ == "__main__":
    main()
