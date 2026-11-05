## EchoID

This is an AI driven website that allows users to identify the speakers in streaming or recorded audio and what they are saying. The user provides the recorded or live audio and the system identifies who are the speakers and what they said.

The user can then download the result as json, pdf or text file.

The user should be able to browse previous work, as well as delete them.

A dashboard should be present for the user to view and purchase credits

A payments and billing page should be present. The application uses a credit based system, not a monthly subscription. The payment uses MPesa and the Kenyan shilling as the currency. The user can pay using an stk push, a paybill or a till number as well as by scanning a qr code. Card payment is also enabled as fallback.

Inlude a registration and login page that uses password based authentication but also intergrates with Google OAuth through firebase.

## Application Flow
- For a new user:
    1. They land on the landing page
    2. They then proceed to the product page (they do not have to register or log in)
    3. They can then generate once
    4. To download the results, they have to register or sign in

- For other users:
    1. They sign in or register
    2. They proceed to the dashboard page
    3. They can generate, view their generations, purchase tokens.

## Technologies
- Use domain driven design to craft the application. 
- Use rich domain models and domain events to communicate between different services. The domain models should use dataclasses, while at the API layer use pydantic for requests and responses validation
- The application should be a monolith
- Use FastAPI for the backend, with postgresql as the database and sqlalchemy as the orm. Make sure to use a virtual environment during development.
- Keep all the configurations in a dotenv file and create a global config object
- Use html, css and javascript for the frontend
- For payments, use MPesa intergrations and the currency unit is Kenyan shillings. The user should be able to pay by:

    1. Getting an STK push on their phone
    2. Paying via till or paybill
    3. Scanning a qr code
- As a fallback option implement payment by card

- For the front end include a minimal landing page, with the hero section and a how it works section. Also include a register and login page as well as a dashboard page, payments and billing pages, a gallery of all the previous generations. Build out the product page. For guidance, an image is provided, showing the landing page for a similar transcription website. Repurpose the transcription site for this product.




