import spacy
import he_ner_news_trf

print("Imported he_ner_news_trf")

try:
    nlp = spacy.load("he_ner_news_trf")
    print("Successfully loaded model via spacy.load")
except Exception as e:
    print(f"Failed to load via spacy.load: {e}")

try:
    nlp = he_ner_news_trf.load()
    print("Successfully loaded model via module.load()")
except Exception as e:
    print(f"Failed to load via module.load(): {e}")
