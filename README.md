

# Twilio-OpenAI-Realtime-Voice-Bot

## Overview

The **Twilio-OpenAI-Realtime-Voice-Bot** is an application that integrates Twilio's Voice API with OpenAI's Realtime API to facilitate real-time voice interactions. This bot allows users to engage in natural, spoken conversations, leveraging advanced AI capabilities to understand and respond to user inputs.

## Features

- **Real-Time Voice Interaction**: Engage in live conversations with the bot through voice calls.
- **AI-Powered Responses**: Utilizes OpenAI's Realtime API to generate contextually relevant and coherent responses.
- **Seamless Integration**: Combines Twilio's telephony services with OpenAI's language models for a smooth user experience.

## Prerequisites

Before setting up the project, ensure you have the following:

- **Twilio Account**: Sign up at [Twilio](https://www.twilio.com/) and obtain a phone number with Voice capabilities.
- **OpenAI API Access**: Register at [OpenAI](https://www.openai.com/) and acquire an API key with Realtime API access.
- **Python 3.9+**: Ensure Python is installed on your system. You can download it from the [official Python website](https://www.python.org/downloads/).
- **Ngrok**: Useful for exposing your local server to the internet during development. Download it from [ngrok](https://ngrok.com/).

## Installation

1. **Clone the Repository**:

   ```bash
   git clone https://github.com/shelenderrkumar/Twilio-OpenAI-Realtime-Voice-Bot.git
   cd Twilio-OpenAI-Realtime-Voice-Bot
   ```

2. **Set Up a Virtual Environment** (Optional but recommended):

   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows, use venv\Scripts\activate
   ```

3. **Install Dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables**:

   Create a `.env` file in the root directory and add the following variables:

   ```env
   TWILIO_ACCOUNT_SID=your_twilio_account_sid
   TWILIO_AUTH_TOKEN=your_twilio_auth_token
   TWILIO_PHONE_NUMBER=your_twilio_phone_number
   OPENAI_API_KEY=your_openai_api_key
   ```

   Replace `your_twilio_account_sid`, `your_twilio_auth_token`, `your_twilio_phone_number`, and `your_openai_api_key` with your actual credentials.

## Usage

1. **Start Ngrok**:

   ```bash
   ngrok http 5000
   ```

   Note the forwarding URL provided by ngrok (e.g., `https://abcd1234.ngrok.io`).

2. **Configure Twilio Webhook**:

   In your Twilio console, set the Voice webhook of your Twilio phone number to point to your ngrok URL followed by `/voice` (e.g., `https://abcd1234.ngrok.io/voice`).

3. **Run the Application**:

   ```bash
   python main.py
   ```

4. **Make a Call**:

   Dial your Twilio phone number to interact with the voice bot.

## Project Structure

- `main.py`: The main application file that sets up the server and handles incoming voice calls.
- `requirements.txt`: Lists the Python dependencies required for the project.
- `.env`: Contains environment variables for configuration (not included in the repository for security reasons).

## Contributing

Contributions are welcome! Please fork the repository and submit a pull request with your proposed changes.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Twilio](https://www.twilio.com/) for providing robust telephony services.
- [OpenAI](https://www.openai.com/) for their advanced language models.

---

*Note: This README is based on standard practices for integrating Twilio and OpenAI APIs. For specific implementation details, please refer to the source code in this repository.* 
