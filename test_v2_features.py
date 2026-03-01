import unittest
import os
import sqlite3
import memory
from ai_coach import get_coach_response, get_coach_summary

class TestHealthCoachV2(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        # Ensure DB is initialized
        memory.init_db()
        cls.test_user_id = 99999999  # Dummy ID for testing
        
        # Mock the AI client so we don't need a real API key to run tests
        from unittest.mock import patch
        import os
        ai_provider = os.getenv("AI_PROVIDER", "gemini").lower()
        
        if ai_provider == "nvidia":
            cls.patcher = patch('ai_coach.openai_client.chat.completions.create')
            cls.mock_create = cls.patcher.start()
            
            # Configure mock to return a dummy response
            class MockMessage:
                def __init__(self, content):
                    self.content = content
            class MockChoice:
                def __init__(self, message):
                    self.message = message
            class MockResponse:
                def __init__(self, choices):
                    self.choices = choices
                    
            cls.mock_create.return_value = MockResponse([MockChoice(MockMessage("Awesome job logging 190 lbs! You also burned 300 calories running."))])
        else:
            cls.patcher = patch('ai_coach.genai_client.models.generate_content')
            cls.mock_create = cls.patcher.start()
            
            class MockResponse:
                def __init__(self, text):
                    self.text = text
            
            cls.mock_create.return_value = MockResponse("Awesome job logging 190 lbs! You also burned 300 calories running.")
        
    @classmethod
    def tearDownClass(cls):
        cls.patcher.stop()
        
    def test_1_database_tables(self):
        """Verify the new weight_logs table exists."""
        conn = sqlite3.connect(memory.DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='weight_logs'")
        table = cursor.fetchone()
        conn.close()
        self.assertIsNotNone(table, "weight_logs table is missing!")

    def test_2_weight_logging_db(self):
        """Test manually logging weight and retrieving it in weekly logs."""
        memory.log_weight(self.test_user_id, 185.5)
        
        # Verify it shows up in the summary
        logs = memory.get_weekly_logs(self.test_user_id)
        self.assertIn("185.5", logs, "Weight log did not appear in the weekly summary context.")
        
    def test_3_ai_weight_parsing(self):
        """Test that the AI system prompt parses and saves weight automatically."""
        # Send a message saying I weight 190 lbs
        context = memory.get_recent_context(self.test_user_id)
        reply = get_coach_response(self.test_user_id, "I stepped on the scale today, I am 190 lbs.", context)
        
        # Check if AI model saved it to DB through our regex extractor
        conn = sqlite3.connect(memory.DB_FILE)
        cursor = conn.cursor()
        cursor.execute('SELECT weight_lbs FROM weight_logs WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1', (self.test_user_id,))
        last_weight = cursor.fetchone()
        conn.close()
        
        self.assertIsNotNone(last_weight)
        self.assertEqual(last_weight[0], 190.0, "The regex extractor failed to pull out the 190 lbs weight!")
        
    def test_4_ai_workout_parsing(self):
        """Test that AI model understands workouts without crashing."""
        context = memory.get_recent_context(self.test_user_id)
        reply = get_coach_response(self.test_user_id, "I just ran for 30 minutes on the treadmill.", context)
        
        # We don't have a rigid DB test for this right now, but we want to make sure it doesn't crash 
        # and inherently acknowledges the workout.
        self.assertTrue(len(reply) > 10, "AI model failed to generate a response to the workout.")

if __name__ == '__main__':
    unittest.main()
