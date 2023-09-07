from googleapiclient.discovery import build
import streamlit as st
import pymongo
from pymongo import MongoClient
from googleapiclient.errors import Error
from googleapiclient.errors import HttpError
from sqlalchemy import create_engine, MetaData, Table
from sqlalchemy import create_engine
import pymysql
import mysql.connector
import pandas as pd
import json
import traceback
import re
import base64

API_KEY = "api"
ATLAS_USERNAME = 'user_name'
ATLAS_PASSWORD = 'password'
MONGO_CONNECTION_STRING = f"mongodb+srv://{ATLAS_USERNAME}:{ATLAS_PASSWORD}@cluster0.ncrxzez.mongodb.net/"
MYSQL_CONNECTION_STRING = "mysql+mysqlconnector://root:123456@localhost/Youtubeproject"

#mongodb and MYSQL connection
mongo_client = MongoClient(MONGO_CONNECTION_STRING)
db = mongo_client["youtube_data"]
collection = db["channel_data"]
engine = create_engine(MYSQL_CONNECTION_STRING)

def get_channel_data(youtube, channel_id): # get channel data
    videoData = []
    request = youtube.channels().list(
        part="snippet,contentDetails,statistics",
        id=channel_id
    )
    response = request.execute()

    for item in response['items']:
        data = {
            'channelId': item['id'],
            'channelName': item['snippet']['title'],
            'subscribers': item['statistics']['subscriberCount'],
            'views': item['statistics']['viewCount'],
            'totalViews': item['statistics']['videoCount'],
            'playlistId': item['contentDetails']['relatedPlaylists']['uploads']
        }
        videoData.append(data)

    return videoData
def get_playlists(youtube, channel_id, max_results=5):#getting playlist from channel_id

    request = youtube.playlists().list(
        part="snippet",
        channelId=channel_id,
        maxResults=max_results
    )
    response = request.execute()

    playlist_data = []

    for item in response.get('items', []):
        data = {
            'playlistId': item['id'],
            'playlistName': item['snippet']['title'],
            'channelId': channel_id
        }
        playlist_data.append(data)

    return playlist_data

def get_video_ids(youtube, playlist_id): # get video id information using playlist id
    video_ids = []
    next_page_token = None

    while True:
        request = youtube.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=playlist_id,
            maxResults=10,
            pageToken=next_page_token
        )
        response = request.execute()

        for item in response['items']:
            video_ids.append(item['contentDetails']['videoId'])

        next_page_token = response.get('nextPageToken')

        if not next_page_token:
            break

    return video_ids
def get_video_details(youtube, video_ids):  # getting all videos information
    All_video_info = []
    for video_id in video_ids:
        request = youtube.videos().list(
            part="statistics,contentDetails,snippet",
            id=video_id
        )
        response = request.execute()

        for item in response['items']:
            AllVideo = {}
            AllVideo["videoId"] = video_id,
            AllVideo['channelId'] = item['snippet']['channelId'],
            AllVideo["video_name"] = item['snippet']['title']
            AllVideo['video_description'] = item['snippet']['description']
            AllVideo['vide0_tags'] = item['snippet'].get('tags', [])
            AllVideo['video_PublishedAt'] = item['snippet']['publishedAt']
            AllVideo['video_View_Count'] = item['statistics']['viewCount']
            AllVideo['video_Like_Count'] = item['statistics'].get('likeCount', [])
            AllVideo['video_Favorite_Count'] = item['statistics'].get('favoriteCount', 0)
            AllVideo['video_Comment_Count'] = item['statistics'].get('commentCount', 0)
            AllVideo['video_Duration'] = item['contentDetails']['duration']
            AllVideo["video_thumbnails"] = item['snippet']['thumbnails']
            AllVideo['video_Caption_Status'] = item['contentDetails']['caption']
            comments = get_video_comments(youtube, video_id)
            AllVideo['video_comments'] = comments

            All_video_info.append(AllVideo)

    return All_video_info
def get_video_comments(youtube, video_id): # getting comments using video id
  try:
        request = youtube.commentThreads().list(
        part = 'snippet',
        videoId= video_id,
        maxResults = 10,
        )
        response = request.execute()

        comments = []

        for item in response['items']:
          cmnt_det = {}
          cmnt_det['commentId'] = item['id']
          cmnt_det["videoid_cmnt"] = video_id
          cmnt_det["cmnt_person"] = item['snippet']['topLevelComment']['snippet']['authorDisplayName']
          cmnt_det["cmnt_TXT_display"] = item['snippet']['topLevelComment']['snippet']['textDisplay']
          cmnt_det["cmnt_PublishedAtl"] = item['snippet']['topLevelComment']['snippet']['publishedAt']
          comments.append(cmnt_det)
        return comments
  except HttpError as e:
        print("An HTTP error %d occurred:\n%s" % (e.resp.status, e.content))


import re


def parse_duration_to_seconds(duration):#fun for converting the time format to requested format using import re
    
    match = re.search(r'(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration)

    if match:
        hours, minutes, seconds = match.groups()

        # Handle None values (if hours, minutes or seconds are not provided)
        hours = int(hours) if hours else 0
        minutes = int(minutes) if minutes else 0
        seconds = int(seconds) if seconds else 0

        total_seconds = hours * 3600 + minutes * 60 + seconds
        return total_seconds
    else:
        return 0


def migrate_channel_data_from_mongo_to_mysql(channelName=None):
    
    if channelName:
        i = collection.find({"Channel_data.channelName": channelName})
    else:
        i = collection.find()  # Fetches all data
    st.write("Migration started...")
    All_data = []
    for i in collection.find():
        data = {
            'channelId': i['Channel_data'][0]['channelId'],
            'channelName': i['Channel_data'][0]['channelName'],
            'subscribers': i['Channel_data'][0]['subscribers'],
            'views': i['Channel_data'][0]['views'],
            'totalViews': i['Channel_data'][0]['totalViews']
        }
        All_data.append(data)

    
    Full_data = pd.DataFrame.from_dict(All_data)

    existing_channel_ids = pd.read_sql('SELECT channelId FROM channel_data', con=engine)#filter method
    Full_data = Full_data[~Full_data['channelId'].isin(existing_channel_ids['channelId'])]

    # Store channel data to SQL
    Full_data.to_sql(name='channel_data', con=engine, if_exists='append', index=False)

    # playlist and process the playlist on mongdb to insert into sql
    playlist_data_list = []
    for i in collection.find():
        for playlist in i.get('video_playlistID', []):
            data = {
                'playlistId': playlist['playlistId'],
                'channelId': playlist['channelId'],
                'playlistName': playlist['playlistName']
            }
            playlist_data_list.append(data)

    
    Full_playlists = pd.DataFrame(playlist_data_list)

    # Filter
    existing_playlists = pd.read_sql('SELECT playlistId FROM video_playlistid', con=engine)
    Full_playlists = Full_playlists[~Full_playlists['playlistId'].isin(existing_playlists['playlistId'])]

    
    Full_playlists.to_sql(name='video_playlistid', con=engine, if_exists='append', index=False)

    # this is for video data
    video_data_list = []
    for i in collection.find():
        for video in i['Video_info']:
            data = {
                'videoId': video['videoId'][0] if isinstance(video['videoId'], list) else video['videoId'],
                'channelId': video['channelId'][0] if isinstance(video['channelId'], list) else video['channelId'],
                'video_name': video['video_name'],
                'video_description': video['video_description'],
                'video_tags': ', '.join(video['vide0_tags']),
                'video_PublishedAt': video['video_PublishedAt'],
                'video_View_Count': video['video_View_Count'],
                'video_Like_Count': video.get('video_Like_Count', 0),
                'video_Favorite_Count': video.get('video_Favorite_Count', 0),
                'video_Comment_Count': video.get('video_Comment_Count', 0),
                'video_Duration': parse_duration_to_seconds(video['video_Duration']),
                'video_thumbnails': json.dumps(video['video_thumbnails']),
                'video_Caption_Status': video['video_Caption_Status']
            }
            video_data_list.append(data)
    Full_video_data = pd.DataFrame(video_data_list)

    # Filter
    existing_video_data = pd.read_sql('SELECT videoId from video_info', con=engine)
    Full_video_data = Full_video_data[~Full_video_data['videoId'].isin(existing_video_data['videoId'])]
    Full_video_data.to_sql(name='video_info', con=engine, if_exists='append', index=False)

    # 4. this is for comments
    comment_data_list = []
    for i in collection.find({"video_comments": {"$exists": True}}):  # Filtering directly in the find query
        for comment in i.get('video_comments', []):
            data = {
                'videoid_cmnt': comment.get('videoid_cmnt', 'N/A'),
                'cmnt_person': comment.get('cmnt_person', 'N/A'),
                'cmnt_TXT_display': comment.get('cmnt_TXT_display', 'N/A'),
                'cmnt_PublishedAt': comment.get('cmnt_PublishedAtl', 'N/A')
            }
            comment_data_list.append(data)

    Full_comments = pd.DataFrame(comment_data_list)
    # Filter 
    existing_video_comments = pd.read_sql('SELECT videoid_cmnt FROM video_comments', con=engine)
    Full_comments = Full_comments[~Full_comments['videoid_cmnt'].isin(existing_video_comments['videoid_cmnt'])]
    if not Full_comments.empty:
        Full_comments.to_sql(name='video_comments', con=engine, if_exists='replace', index=False)
    else:
        st.write("No comments data available to save to SQL.")

def get_channel_names():
    channels = collection.find({}, {"Channel_data.channelName": 1, "_id": 0})
    return [channel["Channel_data"][0]["channelName"] for channel in channels]
import pandas as pd
import mysql.connector
from sqlalchemy import create_engine

mydb = mysql.connector.connect(
    host="localhost",
    user="root",
    password="123456",
    database="Youtubeproject"
)
connection_string = "mysql+mysqlconnector://root:1234@localhost/Youtubeproject"
engine = create_engine(connection_string)
def display_faq():#for sql queries
    questions = {
        '1. What are the names of all the videos and their corresponding channels?': """
        SELECT video_info.video_name, channel_data.channelName
        FROM video_info
        JOIN channel_data ON video_info.channelId = channel_data.channelId;
        """,
        '2. Which channels have the most number of videos, and how many videos do they have?': """
        SELECT channel_data.channelName, COUNT(video_info.videoId) as video_count
        FROM video_info
        JOIN channel_data ON video_info.channelId = channel_data.channelId
        GROUP BY channel_data.channelName
        ORDER BY video_count DESC;
        """,
        '3. What are the top 10 most viewed videos and their respective channels?':"""
        
        SELECT video_info.video_name, channel_data.channelName, video_info.video_view_count 
        FROM video_info
        JOIN channel_data ON video_info.channelId = channel_data.channelId
        ORDER BY video_info.video_view_count DESC
        LIMIT 10;
        """,
        '4. What is the average duration of all videos in each channel, and what are their corresponding channel names?':"""
        
        SELECT channel_data.channelName, AVG(video_info.video_duration) AS avg_duration
        FROM video_info
        JOIN channel_data ON video_info.channelId = channel_data.channelId
        GROUP BY channel_data.channelName;
        """,
        '5. How many comments were made on each video, and what are their corresponding video names?':"""
        
        SELECT video_name, video_Comment_Count 
        FROM video_info
        ORDER BY video_Comment_Count DESC;
        """,
        '6. Which videos have the highest number of likes, and what are their corresponding channel names?':"""
        
        SELECT video_name, video_Like_Count 
        FROM video_info
        ORDER BY video_Comment_Count DESC;
        """,
        '7. What is the total number of likes for each video, and what are their corresponding video names?':"""
        
        SELECT video_name, video_Like_Count 
        FROM video_info
        ORDER BY video_Like_Count DESC;
        """,
        '8. What is the total number of views for each channel, and what are their corresponding channel names?':"""
        
        SELECT channel_data.channelName, SUM(video_info.video_View_Count) as total_views
        FROM video_info
        JOIN channel_data ON video_info.channelId = channel_data.channelId
        GROUP BY channel_data.channelName
        ORDER BY total_views DESC;
        """,
        '9. What are the names of all the channels that have published videos in the year 2022?':"""
        
        SELECT DISTINCT channel_data.channelName
        FROM video_info
        JOIN channel_data ON video_info.channelId = channel_data.channelId
        WHERE YEAR(video_info.video_PublishedAt) = 2022;
        """,
        '10. Which videos have the highest number of comments, and what are their corresponding channel names?':"""
        
        SELECT video_info.video_name, channel_data.channelName, video_info.video_Comment_Count 
        FROM video_info
        JOIN channel_data ON video_info.channelId = channel_data.channelId
        ORDER BY video_info.video_Comment_Count DESC
        LIMIT 10;
        """
    }
    selected_question = st.selectbox('Select a Question:', list(questions.keys()))

    query = questions[selected_question]
    result = pd.read_sql(query, mydb)
    st.write(result)


def main():
    logo = "data:image/png;base64,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"

    st.image(logo, caption='YouTube Logo', use_column_width=True)
    # Sidebar for navigation
    st.sidebar.title("Navigation")
    selection = st.sidebar.radio("Go to", ["Home", "Data Extraction", "Data Transaction", "Data Load & Warehouse", "About"])

    if selection == "Home":
        st.title("Project Details")
        st.write("""
        ## Features:

        * Channel Overview: Get a quick overview of the channel, including its name, description, and subscriber count. This gives you a snapshot of the channel's popularity and focus. Upon overview of channel, we can proceed with harvest option to collect complete information about the channel and store it in our databae

        * No Structured Data Storage: We store the retrieved channel information in our MongoDB database. This ensures that the data is securely stored and readily available for future use.

        * Migration to PostgreSQL: To enhance data analysis and reporting capabilities, we migrate the stored channel information to a structured PostgreSQL database. This allows for efficient querying and data manipulation, enabling us to extract valuable insights from the stored data.

        * Currently, we are in the first stage of our YouTube analytics project which focuses on Data warehouse for the channels. To make it easier to get answers, we've added a tab entitled "Data warehouse" that will give responses based on Extracted channels.

        * Our web application leverages the power of YouTube's API and combines it with the versatility of MongoDB and PostgreSQL databases. This combination ensures a seamless user experience while providing robust data management and analysis capabilities.

        * Start exploring YouTube channels like never before! Enter the YouTube channel ID, and our web application will provide you with a comprehensive overview of the channel, its latest and popular videos, and much more.

        Enjoy your journey through the world of YouTube channels with our web application!.
        """)

    elif selection == "Data Extraction":
        st.title("YouTube Data Harvesting and Warehousing App")

        
        youtube = build('youtube', 'v3', developerKey=API_KEY)

        # Number of channels input
        num_channels = st.number_input("Enter the number of YouTube Channels (Max 10)", min_value=1, max_value=10, value=1)

        with st.form("channel_form"):
            channel_ids = [st.text_input(f"Enter Channel ID {i + 1}") for i in range(num_channels)]
            submit_button = st.form_submit_button("Retrieve Channel Data")

        if submit_button:
            for channel_id in channel_ids:
                st.write(f"Loading data for Channel ID: {channel_id}...")
                # Fetch channel and video data
                channel_stats = get_channel_data(youtube, channel_id)
                video_ids = get_video_ids(youtube, channel_stats[0]['playlistId'])

                all_video_comments = []
                for video_id in video_ids:
                    try:
                        comments = get_video_comments(youtube, video_id)
                        all_video_comments.extend(comments)
                    except Exception as e:
                        # st.error(f"An error occurred while fetching comments: {e}")
                        pass

                video_data = get_video_details(youtube, video_ids)
                video_playlistID = get_playlists(youtube, channel_id, max_results=5)

                # Store data in MongoDB
                data = {
                    "Channel_data": channel_stats,
                    "video_playlistID": video_playlistID,
                    "Video_info": video_data,
                    "video_comments": all_video_comments
                }
                collection.insert_one(data)
                st.write("Data stored successfully in MongoDB")

    elif selection == "Data Transaction":
        st.title("Data migration from Mongodb to SQL")

        # Dropdown to select channel name
        channel_names = get_channel_names()
        selected_channel = st.selectbox("Select a Channel to Migrate", channel_names)

        if selected_channel:
            # Fetch the data for this selected channel from MongoDB
            channel_data = collection.find_one({"Channel_data.channelName": selected_channel})

            # Display channel and video data as tables
            st.subheader("Channel Data")
            st.write(pd.DataFrame(channel_data['Channel_data']))

            st.subheader("Video Data (First 5 entries)")
            st.write(pd.DataFrame(channel_data['Video_info']).head(5))  # Displaying only the first 5 video data

            # Display a button for migration
            if st.button(f"Migrate Data for {selected_channel} from MongoDB to MySQL"):
                try:
                    # Migrate data of the selected channel
                    migrate_channel_data_from_mongo_to_mysql(selected_channel)
                    st.success(f"Data for {selected_channel} successfully migrated!")
                except Exception as e:
                    st.error(f"An error occurred: {e}")
    elif selection == "Data Load & Warehouse":
        display_faq()
    elif selection == "About":
        st.title("YouTube Data Harvesting & Warehouse")
        st.write("""
        This project aims to develop a user-friendly Streamlit application that utilizes the Google API to extract information on a YouTube channel, stores it in a MongoDB database, migrates it to a SQL data warehouse, and enables users to search for channel details and join tables to view data in the Streamlit app.
        """)
        st.subheader("Applications and Packages Used:")
        st.markdown(
            """
            * Pycharm
            * SQL workbench
            * streamlit
            * pandas
            * pymongo
            """
        )

        st.subheader("For any query, connect me on:")
        st.markdown(
            """
            [LinkedIn](https://www.linkedin.com/in/shiva-raj-77039822a)
            [GitHub](https://github.com/Shiva-kalyanaram)
            """
        )

        st.subheader("Thank you for using our App")


if __name__ == "__main__":
    main()
