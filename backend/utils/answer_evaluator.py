from openai import OpenAI
import os
import re
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
import nltk

# Initialize NLTK resources
try:
    nltk.data.find('tokenizers/punkt')
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('punkt')
    nltk.download('stopwords')

# Set the API key directly
api_key = "6f70706e611fa0b4510b85c6e89830a7e0063795f56b88670707282a83a1eea0"
os.environ["TOGETHER_API_KEY"] = api_key

# Create client instance
client = OpenAI(
    base_url="https://api.together.xyz/v1",
    api_key=api_key
)

def preprocess_text(text):
    """Basic text preprocessing"""
    # Convert to lowercase
    text = text.lower()
    
    # Remove special characters and numbers
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\d+', ' ', text)
    
    # Tokenize
    tokens = word_tokenize(text)
    
    # Remove stopwords
    stop_words = set(stopwords.words('english'))
    tokens = [word for word in tokens if word not in stop_words]
    
    # Join tokens back into a string
    return ' '.join(tokens)

def extract_keywords(text):
    """Extract important technical concepts from text"""
    try:
        # Use LLM to extract key technical concepts
        prompt = f"""
        Extract the 5-8 most important technical concepts or key points from this text that would be essential for a correct answer:
        
        {text}
        
        Return only the key technical concepts as a comma-separated list, with no additional text.
        """
        
        response = client.chat.completions.create(
            model="mistralai/Mixtral-8x7B-Instruct-v0.1",
            messages=[
                {"role": "system", "content": "You extract essential technical concepts from text."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=100
        )
        
        keywords_text = response.choices[0].message.content.strip()
        
        # Clean and split keywords
        keywords = [kw.strip() for kw in keywords_text.split(',') if kw.strip()]
        return keywords
    except Exception as e:
        print(f"Error extracting keywords: {str(e)}")
        
        # Fallback to simple frequency-based extraction
        words = preprocess_text(text).split()
        word_freq = {}
        for word in words:
            if len(word) > 3:  # Only consider words longer than 3 chars
                word_freq[word] = word_freq.get(word, 0) + 1
        
        # Sort by frequency and return top 5
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        return [word for word, freq in sorted_words[:5]]

def compare_and_provide_feedback(user_answer, expected_answer):
    """Directly compare user answer with expected answer and provide detailed feedback"""
    try:
        prompt = f"""
        You are providing detailed feedback on a technical interview answer. Be specific, constructive, and direct.
        
        Expected Answer:
        {expected_answer}
        
        User's Answer:
        {user_answer}
        
        Provide specific feedback by:
        1. Start with what the user did well (if anything)
        2. Clearly identify which key technical concepts were missing or incorrect
        3. Point out any misconceptions or errors
        4. Suggest specific improvements with examples
        5. Mention any additional points that would strengthen the answer
        
        Be direct and specific. Don't use generic phrases like "your answer has been recorded" or "consider reviewing". 
        Give actionable, technical feedback that helps them improve their interview performance.
        Keep the feedback concise but comprehensive - around 3-4 sentences maximum.
        """
        
        response = client.chat.completions.create(
            model="mistralai/Mixtral-8x7B-Instruct-v0.1",
            messages=[
                {"role": "system", "content": "You provide specific, actionable technical interview feedback without generic phrases."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=200
        )
        
        feedback = response.choices[0].message.content.strip()
        
        # Remove any generic phrases that might slip through
        generic_phrases = [
            "your answer has been recorded",
            "consider reviewing",
            "you can review",
            "has been noted",
            "feedback is recorded"
        ]
        
        feedback_lower = feedback.lower()
        for phrase in generic_phrases:
            if phrase in feedback_lower:
                feedback = feedback.replace(phrase, "").replace(phrase.capitalize(), "")
        
        # Clean up any extra spaces or punctuation
        feedback = ' '.join(feedback.split())
        
        return feedback
        
    except Exception as e:
        print(f"Error generating feedback: {str(e)}")
        
        # Enhanced fallback feedback
        expected_keywords = extract_keywords(expected_answer)
        user_text = user_answer.lower()
        
        missing_keywords = [keyword for keyword in expected_keywords if keyword.lower() not in user_text]
        
        if not missing_keywords:
            return "Good coverage of the main concepts. To improve further, add specific examples and explain the reasoning behind your approach in more detail."
        else:
            missing_concepts = ", ".join(missing_keywords[:3])
            return f"Your answer is missing key concepts: {missing_concepts}. Focus on explaining these areas with specific examples and technical details to provide a more complete response."

# Example usage
if __name__ == "__main__":
    user_answer = "Your test answer here"
    expected_answer = "The expected correct answer here"
    
    feedback = compare_and_provide_feedback(user_answer, expected_answer)
    print("\nFeedback:")
    print(feedback)