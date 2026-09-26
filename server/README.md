# Server

Place backend services and API contracts in this directory.

Responsibilities:

- request validation and authentication
- job orchestration for transcription and generation
- persistence and storage integration
- API documentation and service-level tests

Keep model training and inference implementation in `ml/`. Document local
environment variables in an `.env.example` file when the service is added;
never commit real credentials.
