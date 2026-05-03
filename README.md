# Sailing club car park fullness w/ Playwright and computer vision

Sometimes the sailing club car park is full, and parking gets painful -- I'd rather cycle. What if I could get an estimate of how full the car park is without having to log in to the club portal and check the webcam myself?

This program periodically logs into the club portal site, and spends a while periodically taking snapshots as the camera pans back and forth.

With these images, YOLOv11 is used to count instances of `car` and average it across snapshots. This is used to provide an estimate of occupancy.

## The tech stack

- Language of choice: Python
- Web service: FastAPI
- Scraping suite: Playwright
- Computer vision model: YOLOv11
- Database: sqlite
- Dev tools: OpenCode, Deepseek V4 Pro, Zed

## The outcome

A fun project for learning about CV/YOLO and Playwright. Likely not that actually useful!

## Limitations & lessons

At my sailing club, the camera pans back and forth every few minutes, and so I take 10 samples over a period of time and average the car count. 

From the view of the camera, cars end up hidden behind each other quite often, obscuring the real number of cars, especially if there are vans in the forefront.

The "max cars" number is also an estimate.