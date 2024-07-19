from langchain.vectorstores.chroma import Chroma
from langchain.chat_models.openai import ChatOpenAI
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.schema.output_parser import StrOutputParser
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema.runnable import RunnablePassthrough
from langchain.prompts import PromptTemplate
from langchain.vectorstores.utils import filter_complex_metadata
from langchain.chat_models.openai import ChatOpenAI
from nltk.corpus import stopwords

import pandas as pd
import os

class ChatDataFrame:
    df = pd.read_pickle('df.pkl')
    vector_store = None
    retriever = None
    chain = None 

    def __init__(self):
        self.model = ChatOpenAI(model_name="gpt-4")
        self.text_splitter = RecursiveCharacterTextSplitter(chunk_size=512, chunk_overlap=64)
        self.prompt = PromptTemplate.from_template(
            """
            [INST]<<SYS>> You are a trademark lawyer that will be given a trademark name to search. Use retrieved trademarks to tell if that trademark name exists already or if there are similar trademarks in the database that might cause a conflict. We want to know the status of the requested trademark, so if the trademark name exists, please specify that it exists as well as its status. We also want to know if similar trademarks exist to see if there is a conflict in using that trademark name. Trademarks can have inactive statuses, like DEAD or CANCELLED.  We want to know the status of the requested trademark, so if the trademark name exists, please specify that it exists as well as its status. We also want to know if similar trademarks exist to see if there is a conflict in using that trademark name.  For the most similar trademarks, give a one or two sentence explanation as to why or why not it might be a conflict to the requested trademark. If the potentially conflicting trademake is dead or cancelled, then there is no conflict. Determining whether a trademark conflicts with another trademark involves several key rules and principles: Likelihood of Confusion: The primary consideration is whether the average consumer would be likely to confuse the two trademarks. This is assessed based on the similarity of the marks and the goods/services they represent. Similarity of the Marks: Visual Similarity: How similar the trademarks look. Phonetic Similarity: How similar the trademarks sound when spoken. Conceptual Similarity: Whether the trademarks convey similar ideas or meanings. Similarity of the Goods/Services: If the goods or services offered under the trademarks are related or fall into the same category, there is a higher chance of confusion. Strength of the Mark: Distinctiveness: More distinctive or unique trademarks are given broader protection. Fame: Well-known trademarks have stronger protection against similar marks. Channels of Trade: The channels through which the goods or services are marketed and sold. If the channels are the same or overlapping, the likelihood of confusion increases. Target Consumers: The typical consumers of the goods/services. If the consumers are likely to overlap, confusion is more likely. Actual Confusion: Evidence of actual confusion among consumers can strongly indicate a conflict, though it is not required to prove a likelihood of confusion. Intent of the Alleged Infringer: If there is evidence that the newer trademark was adopted with the intent to create confusion or deceive consumers, it strengthens the case for conflict. Market Presence and Coexistence: How long the trademarks have coexisted in the market without actual confusion. Longer periods of peaceful coexistence may suggest no likelihood of confusion. Geographical Considerations: The geographical scope of the trademarks' use. If they are used in different regions without overlap, conflict might be less likely. These rules help assess the overall context and likelihood of consumer confusion, which is the cornerstone of trademark conflict determination. Given these rules and the retrieved trademarks make a definitive statement whether in your judgement the trademark name has an important conflict or whether the trademark name doesn't have an important conflict. Reply as if you are an AI trademark lawyer.<</SYS>> 
            Trademark Search: {question} 
            Retrieved Trademarks: {context} 
            Answer: [/INST]
            """
        )
    
    def ingest(self, df: pd.DataFrame):
        # Convert DataFrame to text
        format_row = lambda row: ', '.join([f"{col}: {val}" for col, val in row.items()])
        texts = df.apply(format_row, axis=1).tolist()

        # Create Document chunks
        #documents = [Document(page_content=text, metadata={}) for text in texts]
        #chunks = self.text_splitter.split_documents(documents)
        #chunks = filter_complex_metadata(chunks)
        embedder = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

        vector_store = Chroma.from_texts(texts=texts, embedding=embedder)
        self.retriever = vector_store.as_retriever(
            search_kwargs={
                'k': 5
            },
        )
        self.chain = ({
            "context" : self.retriever,
            "question" : RunnablePassthrough()
                       }
                        | self.prompt
                        | self.model
                        | StrOutputParser()
                       )


    def filter_trademarks(self, df, term):
        # List of stop words to exclude
        stop_words = set().union(stopwords.words('english'),stopwords.words('spanish'), stopwords.words('portuguese'))
        
        # Split the term into individual words excluding the stopwords
        words = [word for word in term.split() if word.lower() not in stop_words]
        # Escape special characters in each word for regex matching
        escaped_words = [pd.Series([word]).str.replace(r'([-[\]{}()*+?.,\\^$|#\s])', r'\\\1', regex=True).iloc[0] for word in words]
        
        # Create a regex pattern to match the full term or any individual word in the term
        pattern = '|'.join(fr'\b{word}\b' for word in escaped_words)
        
        # Filter rows where 'Trademark_Name' matches the pattern (case insensitive)
        filtered_df = df[df['trademarked_name'].str.contains(pattern, case=False, regex=True)]
        return filtered_df
        
    def ask(self, query: str):
        if not self.chain:
            return "Please ingest data first."
        return self.chain.invoke(query)
    
    def clear(self):
        self.vector_store = None
        self.retriever = None
        self.chain = None
    
    def tm_search(self, term: str):

        filtered_df = self.filter_trademarks(self.df, term)
        
        if filtered_df.empty:
            return "No trademarks found matching the term '{}'.".format(term)
        else:
            results_string = "Found {} trademarks similar to the the term '{}':".format(len(filtered_df), term)
            self.ingest(filtered_df)
            ai_results = self.ask(term)
        return results_string + "\n\n" + ai_results

# Set your OpenAI API key as an environment variable
os.environ['OPENAI_API_KEY'] = ''
