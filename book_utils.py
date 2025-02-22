import subprocess
import MeCab
import epub_meta
from utils import save_base64_image, convert_epub_to_txt, process_japanese_text, parse_sentence, remove_ruby_text_from_epub
from frequency_lists import get_all_frequency_lists, get_frequency

from Book import Book

from pathlib import Path
import hashlib
import mmap
import json
import simplejson
from constants import UPLOAD_FOLDER
import numpy as np 
import pandas as pd 
import matplotlib.pyplot as plt
import plotly.express as px
import plotly.io as pio

def sha256sum(filename: str) -> str:
    """
    Computes the sha256 sum of the given file.
    Arguments:
    filename: str - The path to the file to compute the hash of
    """
    h  = hashlib.sha256()
    with open(filename, 'rb') as f:
        with mmap.mmap(f.fileno(), 0, prot=mmap.PROT_READ) as mm:
            h.update(mm)
    return h.hexdigest()

def process_file(filename: str) -> Book:
    """
    Process the given ebook file and returns a Book
    object describing it. The Book object contains various
    fields like the author, title, cover image, etc. as well
    as the path to a generated .txt file (regardless of input extension)
    that has been processed to allow for easy analysis
    Arguments:
    filename: str - The path to the file
    """
    allowed_extensions = ['epub', 'txt']
    extension = filename.split('.')[-1]

    file_hash = sha256sum(filename)
    book_dir = f'static/books/{file_hash}'
    subprocess.run(f'mkdir -p {book_dir}', shell=True)

    if extension == 'epub':
        return process_epub(filename, book_dir=book_dir, file_hash=file_hash)
    elif extension == 'txt':
        return process_txt(filename, book_dir=book_dir, file_hash=file_hash)
    else:
        raise ValueError(f'Filename extension must be one of {",".join(allowed_extensions)}')

def process_epub(filename: str, book_dir: str, file_hash: str) -> Book:
    """
    Takes an epub file and returns a Book object.
    Arguments:
    filename: str - The path to the epub file
    book_dir: str - The directory the book is in
    file_hash: str - The sha256sum hash of the file
    """
    book_path = remove_ruby_text_from_epub(filename,
                                            new_filename=f"{book_dir}/no-furigana.epub")
    book_metadata = epub_meta.get_epub_metadata(book_path)
    title = book_metadata['title']
    authors = book_metadata['authors']
    image = book_metadata['cover_image_content']

    image_path = save_base64_image(image, f'{book_dir}/cover-image.jpg')
    txt_file = convert_epub_to_txt(book_path, process_text=True)

    book = Book(path=txt_file,
            title=title,
            authors=authors,
            image=image_path,
            file_hash=file_hash,
            book_dir=book_dir
            )
    return book

def process_txt(filename: str, book_dir: str, file_hash: str) -> Book:
    """
    Takes a .txt file and returns a Book object.
    Arguments:
    filename: str - The path to the .txt file
    book_dir: str - The directory the book is in
    file_hash: str - The sha256sum hash of the file
    """
    extension = '.' + filename.split('.')[-1]
    title = filename.split('/')[-1].replace(extension, '')
    book = Book(path=filename,
            title=title,
            authors=[],
            image='',
            file_hash=file_hash,
            book_dir=book_dir
            )
    return book

def analyse_ebook(filename: str) -> object:
    """
    Analayse a ebook containing japanese text, determining various things
    like the length of the book in words/characters, the number of unique
    words and characters used, and the number of words and characters that
    are used once only. Returns and object containing this information.
    Arguments:
    filename: str - The path to the file to analyse
    """

    mt = MeCab.Tagger('-r /dev/null -d /usr/lib/mecab/dic/mecab-ipadic-neologd/')
    book = process_file(filename)
    frequency_lists = get_all_frequency_lists()

    with open(book.path, 'r', encoding='utf-8') as file:
        text = file.read()

    # Analysing characters
    chars = list(text)
    unique_chars = set(text)
    chars_with_uses = sorted([(char, chars.count(char)) for char in unique_chars], key=lambda tup: tup[1], reverse=True)
    chars_used_once = [char for char, count in chars_with_uses if count == 1]

    # analysing words
    words = parse_sentence(text, mt)
    unique_words = set(words)
    words_with_uses = sorted([(word, words.count(word)) for word in unique_words], key=lambda tup: tup[1], reverse=True)
    used_once = [word for word, uses in words_with_uses if uses == 1]

    word_list = [{"word": word,
                  "ocurrences": occurences,
                  "frequency": get_frequency(word, frequency_lists)
                  }
                  for word, occurences in words_with_uses
                  ]
    char_list = [{"character": char, "occurences": occurences} for char, occurences in chars_with_uses]

    book_data = {
        'title': book.title,
        'authors': book.authors,
        'image': book.image,
        'n_words': len(words),
        'n_words_unique': len(unique_words),
        'n_words_used_once': len(used_once),
        'n_chars': len(chars),
        'n_chars_unique': len(unique_chars),
        'n_chars_used_once': len(chars_used_once),
        'words': word_list,
        'chars': char_list,
        'file_hash': book.file_hash
    }

    json_filename = f'{book.book_dir}/book_data.json'
    with open(json_filename, 'w', encoding='utf-8') as file:
            simplejson.dump(book_data, file)
            #json.dump(book_data, file)
    print(f'wrote data to {json_filename}')

    clean_dir(book.book_dir, keep_extensions=['.json', '.jpg', '.png'])
    clean_dir(UPLOAD_FOLDER)
    gethistogram(word_list) 

    return book_data

def clean_dir(directory: str, keep_extensions: list = None) -> None:
    """
    Delete all the files in the given directory, keeping
    the files that have one of the extesnsions given in
    keep_extensions. Returns None
    Arguments:
    directory: str - Path to the directory you want to clean
    keep_extensions: list - List of the extensions you want to keep.
    For example, ['.json', '.jpg', '.png']
    """
    if not keep_extensions:
        keep_extensions = []
    for f in Path(directory).glob("*"):
        if f.is_file():
            extension = f.suffix
            if not extension in keep_extensions:
                f.unlink()

def gethistogram(word_list):
    """
    This functions Creates a pandas dataframe of Range and stars of the data in word_list that has 'netflix' in it.
    Range is the bins of the histogram
    """
    bins =  generatebins(getmaximumfreq(word_list)) #generating the bins
    dic = {"Range": "0-500" ,"Stars": [np.nan]} #Creating the columns of the data framw
    df = pd.DataFrame(dic)
    for i in bins:
        df = df.append({'Range':i,'Stars':0},ignore_index=True) 
    for i in word_list:
        key = 'netflix' #netflix is the key
        if key in i['frequency'].keys():  # element is: i['frequency']['netflix'].frequency
            df = df.append({"Range":bins[getbins(i['frequency']['netflix'].frequency,bins)],"Stars":i['frequency']['netflix'].stars},ignore_index=True)
    stars_design = ["★","★★","★★★","★★★★","★★★★★"]
    fig = px.histogram(df, 'Range',color='Range') # generating the plotly histogram
    pio.write_html(fig, file='Histogram.html')

def getbins(freq_num,bins):
    """
    This function determines which range the number falls into
    example: 100, will fall into the range '0-500' 
    """
    flag=1
    for i in range(len(bins)):
        lst = bins[i].split("-")
        if freq_num >= int(lst[0]) and freq_num < int(lst[1]):
            return i 
    return (len(bins)-1)
        

def generatebins(maximum_num):
    """
    This function generates bins based on the maximum element value 
    """
    a = 0
    b= 500
    lst=[]
    while(b<=maximum_num):
        lst.append(str(a)+"-"+str(b))
        a=b
        b=b+500
    return lst

def getmaximumfreq(word_list):
    """
    This functions gets the highest frequency value of the word
    """
    maximum_num = 0
    for i in word_list:
        key = 'netflix'
        if key in i['frequency'].keys():
            maximum_num = max(maximum_num,i['frequency']['netflix'].frequency)
    return maximum_num