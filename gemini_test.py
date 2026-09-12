from google import genai

client = genai.Client()

response = client.models.generate_content(
    model="gemini-3-flash-preview",
    contents="سلام! خودت را در یک جمله معرفی کن."
)

print(response.text)