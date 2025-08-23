# Question Creation Implementation

## Overview
This document describes the implementation of question creation functionality in the MM MVP application, covering both backend (Django) and frontend (Next.js) components.

## Backend Implementation

### Django Models
- **Question Model**: Located in `api/models.py`
  - Fields: `id`, `text`, `tags`, `question_type`, `is_required_for_match`, `created_at`, `updated_at`
  - Supports multiple tags via ManyToManyField
  - Question types: mandatory, answered, unanswered, required, submitted

- **Tag Model**: Located in `api/models.py`
  - Fields: `id`, `name`
  - Predefined choices: value, lifestyle, look, trait, hobby, interest

### API Endpoints
- **POST `/api/questions/`**: Create a new question
  - Uses the existing QuestionViewSet with custom create method
  - Handles tag creation and validation
  - Returns the created question object

### Custom Create Method
Located in `api/views.py` within QuestionViewSet:
- Validates required fields (text, tags)
- Creates the question using the serializer
- Automatically creates or links existing tags
- Handles errors gracefully with proper HTTP status codes

## Frontend Implementation

### API Service
- **Location**: `mmfrontend/src/services/api.ts`
- **Method**: `createQuestion(questionData)`
- **Endpoint**: `/api/questions/`
- **Response**: Returns Question object with ID

### Create Question Page
- **Location**: `mmfrontend/src/app/dashboard/questions/create/page.tsx`
- **Features**:
  - Form validation for required fields
  - Support for 5 answer options
  - Tag selection from predefined list
  - Mandatory/optional question toggle
  - Error handling and display
  - Success redirect to questions list

### Data Flow
1. User fills out the question creation form
2. Frontend validates form data
3. Frontend sends POST request to `/api/questions/`
4. Backend validates data and creates question
5. Backend creates/links tags
6. Backend returns question object
7. Frontend redirects to questions list on success

## Usage Example

### Creating a Question
```typescript
const questionData = {
  text: "What is your favorite color?",
  tags: ["value"],
  question_type: "mandatory",
  is_required_for_match: true,
  answers: [
    { value: "1", answer: "Red" },
    { value: "2", answer: "Blue" },
    { value: "3", answer: "Green" }
  ]
};

const response = await apiService.createQuestion(questionData);
```

### API Response
```json
{
  "id": "uuid-here",
  "text": "What is your favorite color?",
  "tags": [{"id": 1, "name": "value"}],
  "question_type": "mandatory",
  "is_required_for_match": true,
  "created_at": "2025-08-23T03:30:34.050645Z",
  "updated_at": "2025-08-23T03:30:34.050655Z"
}
```

## Error Handling

### Backend Validation
- Question text required and max 1000 characters
- At least one tag required
- Proper HTTP status codes (400, 500)

### Frontend Validation
- Form field validation
- API error handling
- User-friendly error messages
- Loading states during API calls

## Security Features
- CSRF protection via Django's built-in middleware
- Input validation and sanitization
- Proper error handling without exposing internal details

## Testing
- Backend functionality verified with test script
- Models, serializers, and view logic tested
- Tag creation and linking verified

## Future Enhancements
- Answer validation and storage
- Question approval workflow
- Bulk question creation
- Question templates
- Advanced tag management
