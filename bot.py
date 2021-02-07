"""
This is a module that defines a bot to interact with telegram users.
The main function of the bot is to guide users wherever they want to go within
a limited region although it has awesome features.

context.user_data will store the data related to each user with this format.
'loc': A (longitude, latitude) tuple of the current location.
'last_time': The last time we received information from the user.
'target': The destination the user wants to go.
'route': A list with the route values.
'checkpts': The number of checkpoints the route has.
'curr_chkpt': The current checkpoint he is.
'waiting': A boolean value so the bot knows when there is no user response.
'inline-tapped': a list of booleans to avoid the user to repeat inline
                 keyboard button actions.
                 Each boolean represents one action.
"""

import os
import time
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters,
                          CallbackQueryHandler)
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
import osmnx as ox
import guide as gd
import random
from haversine import haversine


# Create error handlers.
class Error(Exception):
    pass


class NoTargetError(Error):
    pass


class TooNearError(Error):
    pass


class NoDestinationError(Error):
    pass


# Constants declaration.
PLACE = "Barcelona"  # The working zone of the bot.
NEAR_DST = 20  # A user is on a checkpoint with this radius.
AWAY_DST = 80  # A user may be getting lost with this radius.
FAR_AWAY_DST = 250  # A user is lost with this radius.
MAX_TIME = 240  # Time to consider a user is no longer sharing its location.
N = 3  # Maximum checkpoints the user can skip.


def start(update, context):
    """
    The command to start a conversation with the bot.
    """
    # inline_tapped initialization
    context.user_data['inline_tapped'] = [False]*7

    keyboard = [
                [InlineKeyboardButton("/help", callback_data="help"),
                 InlineKeyboardButton("/authors", callback_data="authors")]
                ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Welcome "+update.effective_chat.first_name+"! Whenever you " +
        "want to start your journey, send me your current location and " +
        "type /go followed by the place you want to go.",
        reply_markup=reply_markup)

    print(update.effective_chat.first_name+" has entered the chat.\n")


def helper(update, context):
    """
    A command that provides the user all things the bot can do.
    """
    context.user_data['inline_tapped'][4] = False

    keyboard = [[InlineKeyboardButton("How do I share my location?",
                                      callback_data="location-help")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Here is all you can do with me! Just write:\n\n" +
        "- /go destiny, to start a guide to your destiny location\n" +
        "- /where, to see where you are\n" +
        "- /recompute, if you want to restart your route\n"
        "- /cancel, to end the current journey\n" +
        "- /author, to see the authors that made this project\n\n" +
        "You can move all around " + PLACE + ".",
        reply_markup=reply_markup)


def _listener(update, context):
    """
    A private function to analyze the messages sent by the user.
    If one seems like a command, the bot will treat it.
    """
    name = update.effective_chat.first_name
    msg = update.message.text.lstrip()

    print(name + ":", msg, "\n")

    # The user can misunderstood the functionality of the bot, so
    # the command 'go' would work like '/go', and the same for other commands.
    if msg[:5] == "start":
        start(update, context)
    elif msg[:4] == "help":
        helper(update, context)
    elif msg[:2] == "go" or msg[1:3] == 'go':
        go(update, context)
    elif msg[:5] == "where":
        where(update, context)
    elif msg[:6] == "cancel":
        cancel(update, context)
    elif msg[:6] == "author":
        authors(update, context)
    elif msg[:9] == "recompute":
        _compute_route(update, context)
    else:
        context.bot.sendChatAction(update.effective_chat.id, "typing")
        try:
            ox.geocode(msg)
            context.user_data['inline_tapped'][5] = False
            keyboard = [[InlineKeyboardButton("Yes, /go "+str(msg),
                                              callback_data="go "+str(msg))],
                        [InlineKeyboardButton("No", callback_data="null")]
                        ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Sorry, I didn't understand that at all.\n" +
                "Did you mean /go "+str(msg)+"?",
                reply_markup=reply_markup)
        except:
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Sorry, I didn't understand that.\nTo know what I can " +
                "do, please type /help and you will see a list of all " +
                "commands.")


def where(update, context):
    """
    A command to see where the user is.
    -----
    Requirements: The user location.
    -----
    Respond: Sends the user a photo containing a map with his location, and
    a message with his coordinates Latitude and Longitude.
    """
    try:
        location = context.user_data['loc'][::-1]

        # Improve the appearence of the chat with the bot.
        context.bot.sendChatAction(update.effective_chat.id, "upload_photo")

        fname = "%d.png" % random.randint(1000000, 9999999)
        gd.plot_directions(None, location, None, None, fname)

        context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=open(fname, 'rb'))
        os.remove(fname)

        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Your current location is :\n" +
            "Latitude: "+str(location[1])+"\n" +
            "Longitude: "+str(location[0])+"\n")

        print("The actual location of " + update.effective_chat.first_name +
              " is: \n" +
              "Latitude: "+str(location[1])+"\n" +
              "Longitude: "+str(location[0])+"\n")

    except KeyError:
        print("No location of " + str(update.effective_chat.first_name) +
              " found.")

        context.user_data['inline_tapped'][4] = False
        keyboard = [[InlineKeyboardButton("How do I share my location?",
                                          callback_data="location-help")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Sorry, it seems you are not sharing your location with us.",
            reply_markup=reply_markup)


def go(update, context):
    """
    A command to start a guide to the place the user wants.
    -----
    Requirements: A string with the place and the user location.
    -----
    Respond: First sends the user a photo containing a map with his route.
    Then, starts sending messages containing information related to the guide
    every time he achieves a new checkpoint.
    """
    try:
        text = update.message.text
        target = text[3:].lstrip()

        if not target:
            raise NoDestinationError

        # Store the target to be useful when recomputing the route.
        context.user_data['target'] = target

        # Call the function that computes the route.
        _compute_route(update, context)

    # Treat all possible errors.
    except NoDestinationError:
        # The user has not sent a destination place.
        print(update.effective_chat.first_name,
              "didn't send a destination.\n")
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="You need to give any destination to go.\n" +
            "Example: '/go Tibidabo.")

    except Exception as e:
        print(e)
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Sorry, we've got an internal error.\n" +
            "Please try again.")


def _compute_route(update, context):
    """
    A private function to compute the route that the user demands.
    """
    try:
        graph = context.bot_data['map']
        location = context.user_data['loc'][::-1]

        # Geocode the destination target.
        if context.user_data.get('target'):
            target = context.user_data['target']
        else:
            raise NoTargetError
        destination = ox.geocode(target)

        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Computing route to " + target + "...")
        # Improves the appearence of the chat with the bot.
        context.bot.sendChatAction(update.effective_chat.id, "typing")

        # Compute the shortest route from location to destination.
        route = gd.get_directions(graph, location, destination)

        print(update.effective_chat.first_name + " started a new " +
              "journey to " + target + ".\n")

        # Store the route and the number of checkpoints on user_data.
        context.user_data['route'] = route
        checkpoints = len(route)
        context.user_data['checkpts'] = checkpoints
        context.user_data['curr_chkpt'] = 0

        # Sent the bot a photo of the trip.
        fname = "%d.png" % random.randint(1000000, 9999999)
        gd.plot_directions(graph, location, destination, route, fname)
        context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=open(fname, 'rb'))
        os.remove(fname)

        # If the route has only two checkpoints, just sent the photo.
        if checkpoints == 2:
            # Invert the coordinates because of haversine function
            mid = route[0]['mid'][::-1]
            distance = round((haversine(location, mid, 'm') +
                              haversine(mid, destination, 'm')))
            raise TooNearError

        # Otherwise guide the user to the first checkpoint.
        msg = _message_route(update, context)
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=msg,
            parse_mode="Markdown")

        # Add a job to the job queue, call _callback_no_response every
        # 60 seconds.
        context.job_queue.start()
        context.job_queue.run_repeating(_callback_no_response, 60, 60,
                                        context={'update': update,
                                                 'context': context})

    # Treat all possible errors.
    except NoTargetError:
        # The user has not a target from a previous route.
        print(update.effective_chat.first_name,
              "has no target destination.\n")
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="You don't have any previous route to recompute.\n" +
            "Start one for example by typing: /go Tibidabo.")
    except TooNearError:
        # The place the user wants to go is just one node or less away.
        print("Destiny of " + update.effective_chat.first_name +
              " too near.\n")
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Your destiny is too near! Just " + str(distance) +
            " meters away!")

    except KeyError:
        # The user is not sharing his location with us.
        print("No location of the user", update.effective_chat.first_name,
              "found.\n")

        context.user_data['inline_tapped'][4] = False

        keyboard = [[InlineKeyboardButton("How do I share my location?",
                                          callback_data="location-help")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Sorry, it seems you are not sharing your location with us.",
            reply_markup=reply_markup)

    except AssertionError as e:
        if str(e)[:11] == "destination":
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Sorry, your destination is not in " + PLACE + ".")
        elif str(e)[:6] == "source":
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Sorry, you are not in " + PLACE + ".")

    except Exception as e:
        print(e)
        # Geocode returned no results for the destination query.
        if (str(e)[:9] == "Nominatim"):
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="It seems *" + target +
                "* is not a place at all, try with other words.",
                parse_mode="Markdown")
        # Another kind of error happened.
        else:
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Sorry, we've got an internal error.\n" +
                "Please try again.")


def _update_and_check(update, context):
    """
    A private function that updates the current location and time of the user
    and checks his current route.
    """
    # Get the location of the user.
    message = (update.edited_message if update.edited_message
               else update.message)

    location = message.location.longitude, message.location.latitude

    # Store the current location and time on his user data.
    context.user_data['loc'] = location
    context.user_data['last_time'] = int(time.time())
    context.user_data['waiting'] = False

    print("The location of", update.effective_chat.first_name, "is:",
          location, ".\n")

    # If the user has an active route, check if he is near a checkpoint.
    if context.user_data.get('route'):
        current = context.user_data['curr_chkpt']
        checkpts = context.user_data['checkpts']

        # If the user is near one of the first N checkpoints, he achieves it.
        # The bigger N is the better it works if the user skips any checkpoint,
        # although we lose temporal efficiency.
        current_distance = None
        is_near = False
        for i in range(N):
            if current + i < checkpts:
                # Distance of the user to the (current+i)-th checkpoint.
                next_chkpt = context.user_data['route'][current + i]['mid']
                current_distance = round(haversine(location[::-1],
                                                   next_chkpt[::-1], 'm'))
                print("The user", update.effective_chat.first_name, "is",
                      current_distance, "meters from #", i, ".\n")

            if current_distance and current_distance < NEAR_DST:
                # Update checkpoint and send the guiding message.
                is_near = True
                context.user_data['curr_chkpt'] = current + i + 1
                message = _message_route(update, context)

                context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=message,
                    parse_mode="Markdown")

                # To send a share button when finished route
                if current + i + 1 == checkpts - 1:
                    share_msg = ("I have travelled to **" +
                                 str(context.user_data['target']) +
                                 "** with this bot, it's amazing! 😄")
                    user_msg = "Yes, share the bot with my friends!"
                    keyboard = [[
                        InlineKeyboardButton(user_msg,
                                             switch_inline_query=share_msg)
                        ]]
                    reply_markup = InlineKeyboardMarkup(keyboard)

                    context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="Did you enjoy your journey?",
                        reply_markup=reply_markup)

                print(str(update.effective_chat.first_name) + " moved to #" +
                      str(current+i+1) + " of #" + str(checkpts-1) + ".\n")

        # Check if the user is getting away from the checkpoint.
        if not is_near:
            next_chkpt = context.user_data['route'][current]['mid']
            current_distance = round(haversine(location[::-1],
                                               next_chkpt[::-1], 'm'))
            # Minimum distance to be sure the user is really going away.
            min_distance = context.user_data['route'][current].get('length')

            # If is getting far away from then recompute the route.
            if min_distance and current_distance > min_distance + FAR_AWAY_DST:
                context.user_data['inline_tapped'][6] = False
                keyboard = [[InlineKeyboardButton("Yes, /recompute ",
                                                  callback_data="recompute"),
                            InlineKeyboardButton("No", callback_data="null")]
                            ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                message = ("It seems that you got lost.\n\n" +
                           "Do you want to recompute your route?")

                context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=message,
                    reply_markup=reply_markup)

            # If is just getting away from the checkpoint only send a message.
            elif min_distance and current_distance > min_distance + AWAY_DST:
                keyboard = [[InlineKeyboardButton("Where am I?",
                                                  callback_data="where")]]
                reply_markup = InlineKeyboardMarkup(keyboard)

                message = ("Be careful, you are walking away! You are at " +
                           str(current_distance) +
                           " meters from the next checkpoint!")

                context.user_data['inline_tapped'][2] = False
                context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=message,
                    reply_markup=reply_markup)

                print(update.effective_chat.first_name, " is walking",
                      "away from his checkpoint.\n")


def _message_route(update, context):
    """
    A private function that guides the user to the next checkpoint through a
    message or if finished it ends the route.
    Returns a string containing the message.
    """
    # Get the stored data related to the user.
    route = context.user_data['route']
    loc = context.user_data['loc']
    current = context.user_data['curr_chkpt']
    last = context.user_data['checkpts'] - 1

    # First iteration
    if current == 0:
        dist = round(haversine(loc[::-1], route[0]['mid'][::-1], 'm'))
        msg = ("You are at " + str(loc) + ".\n"
               "Start at checkpoint #1 of #" + str(last) + ": " +
               str(route[0]['mid']) + ".\n*" + route[0]['next_name'] +
               " at " + str(dist) + " meters.*")

    # Medium iterations
    elif current < last:
        angle = route[current-1].get('angle')
        dist = round(route[current].get('length'))

        # Angle deviation checking
        if angle:
            if 0 < angle < 22.5:
                turn = "Go straight"
            elif angle < 67.5:
                turn = "Turn half right"
            elif angle < 112.5:
                turn = "Turn right"
            # An angle of 180 probably would never be in a route but a
            # stronger turn should be contemplated.
            elif angle < 180:
                turn = "Turn strong right"
            elif angle < 247.5:
                turn = "Turn strong left"
            elif angle < 292.5:
                turn = "Turn left"
            elif angle < 337.5:
                turn = "Turn half left"
            else:
                turn = "Go straight"
        else:
            turn = "Go straight"

        msg = ("Well done! You have reached checkpoint #" + str(current) +
               " of #" + str(last) + "!\n"
               "You are at " + str(loc) + ".\n"
               "Go to checkpoint #" + str(current+1) + " " +
               route[current]['current_name'] + ".\n\n*" +
               turn + " through " + route[current]['current_name'] + " " +
               str(dist) + " meters.*")

    # Last iteration
    else:
        destination = route[-1]['mid'][::-1]
        dist = round(haversine(loc[::-1], destination, 'm'))
        angle = route[current-1].get('angle')

        if angle:
            if 0 < angle < 22.5:
                turn = "in front of you"
            elif angle < 180:
                turn = "at your right"
            elif angle < 337.5:
                turn = "at your left"
            else:
                turn = "in front of you"
        else:
            turn = "in front of you"

        msg = ("Congratulations, last checkpoint achieved! 🥳\n" +
               "*Your destination is " + str(dist) + " meters " + turn +
               " .*\n")

        # Send a photo with the location of the user and its destination
        fname = "%d.png" % random.randint(1000000, 9999999)
        gd.plot_directions(None, loc[::-1], destination, None, fname)
        context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=open(fname, 'rb'))
        os.remove(fname)

        # Delete the route from the user.
        del context.user_data['route']
        del context.user_data['checkpts']
        del context.user_data['curr_chkpt']

    # Return the message we will send to the user to guide him.
    return msg


def _callback_no_response(context):
    """
    Reminds the user to send its location if max_time has passed since
    the last location sent.
    """
    update = context.job.context['update']
    context = context.job.context['context']

    if 'waiting' in context.user_data and not context.user_data['waiting']:
        if time.time() - context.user_data['last_time'] > MAX_TIME:
            context.user_data['inline_tapped'][3] = False
            context.user_data['inline_tapped'][4] = False

            keyboard = [
                [InlineKeyboardButton("Yes, I'll share my location",
                                      callback_data="null"),
                 InlineKeyboardButton("No, cancel route.",
                                      callback_data="cancel")],
                [InlineKeyboardButton("How do I share my location?",
                                      callback_data="location-help")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # To avoid sending multiple messages if the user is not responding
            context.user_data['waiting'] = True
            context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="You haven't moved in a while, maybe your location " +
                    "went off...\nDo you want to continue the route?",
                    reply_markup=reply_markup)


def _button(update, context):
    """
    Handles the queries received from the inline buttons.
    Each button represents one different action.

    The actions are linked with the booleans from user_data['inline_tapped']
    When a button is sent to the user, the boolean from the position of the
    action have to be False.

    Each position to the boolean represents:
        0 : help
        1 : authors
        2 : where
        3 : cancel
        4 : location-help
        5 : go
        6 : recompute
    """

    # Get the action to be performed.
    query = update.callback_query
    action = query['data']

    # To know if the user has tapped twice on the button, booleans from
    # user_data['inline_tapped'] are used.
    # After an action is done, the boolean is set to True to avoid the
    # user from tapping multiple times and getting the same action more than
    # once.
    tapped = context.user_data['inline_tapped']

    if action == "help" and not tapped[0]:
        context.user_data['inline_tapped'][0] = True
        helper(update, context)

    elif action == "authors" and not tapped[1]:
        context.user_data['inline_tapped'][1] = True
        authors(update, context)

    elif action == "where" and not tapped[2]:
        context.user_data['inline_tapped'][2] = True
        where(update, context)

    elif action == "cancel" and not tapped[3]:
        context.user_data['inline_tapped'][3] = True
        cancel(update, context)

    elif action == "location-help" and not tapped[4]:
        context.user_data['inline_tapped'][4] = True
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="1. Tap on the icon 📎 at bottom-right.\n " +
            "2. Tap on *Location*.\n\n3. Select *Share My Live Location " +
            "for...*\n\n4. Select for how long.\n\nDone!",
            parse_mode="Markdown")

    elif action[:2] == "go" and not tapped[5]:
        context.user_data['inline_tapped'][5] = True

        # Saves the place the user want to go to compute a route to there.
        context.user_data['target'] = action[3:]

        _compute_route(update, context)

    elif action == "recompute" and not tapped[6]:
        context.user_data['inline_tapped'][5] = True

        _compute_route(update, context)

    # Stops the loading animation when the button is tapped.
    query.answer()


def cancel(update, context):
    """
    A command to stop the current guide.
    """
    try:
        # Remove all jobs to stop reminding the user if it's still there.
        context.job_queue.stop()

        # Delete the information about the route, except the target.
        del context.user_data['route']
        del context.user_data['checkpts']
        del context.user_data['curr_chkpt']

        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Route succesfully cancelled.")

        print(update.effective_chat.first_name, "has cancelled his route.")

    except Exception as e:
        print(e)
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="There's no route to cancel but you can start a new one.")


def authors(update, context):
    """
    A command to see the authors of the guiding bot and guide module.
    """
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="The authors of this project are:\n" +
        "- Dani Gómez\n" +
        "- David Pujalte\n")


def main():
    # Open the token and the dispatcher of our bot.
    Tkn = open('token.txt').read().strip()
    updater = Updater(token=Tkn, use_context=True)
    dispatcher = updater.dispatcher

    # Set the commands that our bot will handle.
    dispatcher.add_handler(CommandHandler('start', start))
    dispatcher.add_handler(CommandHandler('help', helper))
    dispatcher.add_handler(CommandHandler('go', go))
    dispatcher.add_handler(CommandHandler('recompute', _compute_route))
    dispatcher.add_handler(CommandHandler('where', where))
    dispatcher.add_handler(CommandHandler('cancel', cancel))
    dispatcher.add_handler(CommandHandler('author', authors))

    # Set the chat filters we will use at our functions.
    dispatcher.add_handler(MessageHandler(Filters.text, _listener))
    dispatcher.add_handler(MessageHandler(Filters.location, _update_and_check))

    # Set the Callback Queries to handle.
    dispatcher.add_handler(CallbackQueryHandler(_button))

    # Store the map of the place we want our bot to guide, so this way it
    # does not have to be loaded every time.
    # Download is proceeded if the graph is not on the directory
    try:
        dispatcher.bot_data['map'] = gd.load_graph(PLACE)
        print("Bot started and working in", PLACE, "\n")
        # Start the bot.
        updater.start_polling()
    except:
        print(PLACE + ".gpickle not found, downloading", PLACE, "graph.\n")

        try:
            dispatcher.bot_data['map'] = gd.download_graph(PLACE)
            gd.save_graph(dispatcher.bot_data['map'], PLACE)
            print(PLACE + ".gpickle downloaded at", os.getcwd(), "\n")
            print("Bot started and working in", PLACE, "\n")
            # Start the bot.
            updater.start_polling()
        except:
            print("Can not download the graph from", PLACE, "\nPlease,",
                  "close the bot and change the place in order to start",
                  "the bot.\n")
            # To let the programmer read the message if bot.py is executed on
            # an external terminal.
            time.sleep(5)


if __name__ == '__main__':
    main()
