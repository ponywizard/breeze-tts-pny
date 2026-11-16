import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'server'))
from breeze_pny.speech import breeze_text


class SpeechCues(unittest.TestCase):
    def test_reviewed_cues_and_captured_forms(self):
        for source, expected in [
            ('Teehee! Hello.', '(giggles) Hello.'),
            ('Hello! giggle', 'Hello! (giggles)'),
            ('Gasp! A mountain of frosting!', '(gasp) A mountain of frosting!'),
            ('gasp ...a perfect day!', '(gasp) ...a perfect day!'),
            ('and... and... gasp ...the best jam!', 'and... and... (gasp) ...the best jam!'),
            ('and… gasp …the best jam!', 'and… (gasp) …the best jam!'),
        ]:
            with self.subTest(source=source):
                self.assertEqual(breeze_text(source), expected)
                self.assertEqual(breeze_text(expected), expected)

    def test_dialogue_quotes_and_other_interjections_are_retained(self):
        for text in ['A gasp escaped her.', 'Please gasp again.', 'Gasp for air.',
                     '"Oh! Gasp! Amazing!"', "The word 'Gasp!'", '“Gasp!”', '(gasp) Hello.',
                     'yawn Oooooh, apples!', 'Hmph! Finally!', 'Hehe! Good one!', 'Hahahaha!',
                     'I like your giggle.', '"Teehee!"']:
            with self.subTest(text=text):
                self.assertEqual(breeze_text(text), text)


if __name__ == '__main__':
    unittest.main()
