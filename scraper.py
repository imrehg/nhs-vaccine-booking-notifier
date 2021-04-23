import datetime
import logging
import os
import sys
from collections import namedtuple

import requests
from bs4 import BeautifulSoup
from sqlalchemy import Column, String, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

URL = "https://www.nhs.uk/conditions/coronavirus-covid-19/coronavirus-vaccination/book-coronavirus-vaccination/"

VaccineUpdate = namedtuple("VaccineUpdate", ["date", "criterion"])

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

Base = declarative_base()


class Update(Base):
    __tablename__ = "updates"

    date = Column(String, primary_key=True)
    criterion = Column(String)


def query_website(
    url: str = URL,
) -> VaccineUpdate:
    """Query the NHS website and extract the latest
    update date and (hopefully) the first eligibillity criterion.
    """
    res = requests.get(URL)
    if res.status_code != 200:
        return
    soup = BeautifulSoup(res.text, "html.parser")

    # If only the website used id values, so we could select entries more reliably
    review_dates = list(soup.find_all("div", {"class": "nhsuk-review-date"}))[
        0
    ]
    last_review_text = review_dates.p.text.strip().split("\n")[0]
    last_review_date = last_review_text.split(":")[1].strip()

    parsed_last_review_date = datetime.datetime.strptime(
        last_review_date, "%d %B %Y"
    )

    # If only the website used id values, so we could select entries.
    summary_selector = "#maincontent > article > div > div > section:nth-child(2) > ul > li:nth-child(1)"
    first_criterion = soup.select(summary_selector)[0].text
    result = VaccineUpdate(
        date=parsed_last_review_date.date(), criterion=first_criterion
    )
    logging.debug(f"Latest review date {result.date}")
    return result


def check_and_store(
    vaccine_update: VaccineUpdate,
    database: str = "sqlite:////project/website.db",
) -> bool:
    """Check if the latest vaccine site update is newer
    that in the database or not, and if yes, store the date & message.

    Parameters
    ----------
    vaccine_update: VaccineUpdate
        The vaccine update containing data and first criterion.
    database: str
        The database connection to pass to SQLAlchemy.

    Returns
    -------
    bool:
        True if this update is newer than what was known before.
    """
    engine = create_engine(database)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    new_update = False

    latest_date_query = session.query(Update.date).order_by(Update.date.desc())
    query_result = latest_date_query.first()
    previous_latest_date = (
        datetime.datetime.strptime(query_result[0], "%Y-%m-%d").date()
        if query_result is not None
        else None
    )

    if (
        previous_latest_date is None
        or vaccine_update.date > previous_latest_date
    ):
        logging.info(
            f"New update found: {vaccine_update.date}. Previous date: {previous_latest_date}"
        )
        new_update = True
        update = Update(
            date=str(vaccine_update.date), criterion=vaccine_update.criterion
        )
        session.add(update)
        session.commit()

    return new_update


def send_notification(
    vaccine_update: VaccineUpdate, sender: str, receiver: str, config_path: str
):
    """Send notification message with signal-cli."""
    message = f"Vaccine booking: latest update {vaccine_update.date}, {vaccine_update.criterion} -> {URL}"
    cmd = " ".join(
        [
            "signal-cli",
            "--verbose",
            f'--config "{config_path}"',
            f'--username "{sender}"',
            "send",
            f'--message "{message}"',
            f'"{receiver}"',
        ]
    )
    logging.debug(f"Command: {cmd}")
    os.system(cmd)


if __name__ == "__main__":
    import configparser

    config = configparser.ConfigParser()
    config.read("scraper.ini")

    # Scrape
    latest_update = query_website()
    if latest_update is None:
        sys.exit(1)

    # Check
    new_update = check_and_store(latest_update, config["Database"]["Engine"])

    # Notify if applicable
    if new_update:
        send_notification(
            latest_update,
            config["Notifications"]["Sender"],
            config["Notifications"]["Receiver"],
            config["Notifications"]["ConfigPath"],
        )
