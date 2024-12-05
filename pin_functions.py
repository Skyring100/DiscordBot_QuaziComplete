import RPi.GPIO as GPIO
GPIO.setmode(GPIO.BCM)
led_pin = 16
GPIO.setmode(led_pin, GPIO.OUT)

def change_led(is_on: bool):
    GPIO.output(led_pin, is_on)