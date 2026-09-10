# New update specification

## Regression

- Remove the recipi generation AI features, they where a nice experience, but are not what we want at the end, text & image generation
- Remove image generation, Change the AIgeneration to a user add image, still stored in rustfs, miniature for preview & full. Set no images recipies with a simple color with a light gradient

## Small style improvements

- right of toolbar prepend pp-avatar-button, display username
- Change the v-navigation-drawer\_\_content avatar btn by the app logo
- Move the add ingredient & add step whide btns to a icon btn to the right, aligned with the section title
- Reuse the new reciepe form sections style for the reciepe display
- In the new event form, add a title for the dates explaining their purpose. Is it possible to have a nice single calendar with the from & too with filled days in between, like they do in the Rb&b stuff? YOu can add dependancies.

## New Features

- Add a right click contextual btn to the reciepes cards
- In our user profile, there is different fields to fill what we like / don't like / what we can't eat. It's a mixte of serious (I'm vegan, I don't drink, ...) And more fun "questions" : (Ma favorite ... is) . I'll let you decide, include cheese (we are french), place 10 of them
- Clicking on another user name / profile image opens his public page where we can see his recepies. We can see the answer to the questions of what they eat / don't eat / like / disklike. Empty fields are not displayed.

## The Planificateur feature

Let's make this section of the app useful.
Ask the user, on creation:

- The number of expected people that will eat each day

On click, we can see the event details.
We can edit somewhere the event informations
We see a large calender with the days outside the from to dates unavailable to click, the days of the event are clickable.

On click on a day, we see matin, midi & soir
We can, for each part of the day:

- set that there is no need to cook for this part of the day
- Set how many people will be here (by default the nb decided later)
- Add one or more recipes and tell, for each of them, how many people will eat (the number of serving), by default the nb people of the day
- The available recipes are the user one, but, from another tab, see the other event members recipes. An add recipe shortcut and a search bar that searches all members recipes is also available (results are separated).

We can see on the calendar a short google task style line for each recipes added for this day, or something indicating that there is no need for this part of the day.
We can select them with crtl click and drag them from a part of a day to another day / part of the day. We can also drag single meal

A grocery list btn allows you to generate a grocery list for the whole event by calculating the ingredient lists and the number of people eating. Each item is grouped by "rayon".
An event grocery list is it's own page and can be shared
An LLM calculates the estimated price of each items + total and is displayed
We can check the items box, it's visible to everyone live
A toggle allows to group by recipies instead of category
A progress bar is displayed
A copy contend to text btn is somewhere

The "liste des course" in the app left panel displays an access of all joinded events grocery list sorted by update list
