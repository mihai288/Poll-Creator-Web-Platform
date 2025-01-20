from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import uuid

app = Flask(__name__)
app.secret_key = 'secret'


app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///polls.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


# Modele
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    polls = db.relationship('Poll', backref='creator', lazy=True)


class Poll(db.Model):
    id = db.Column(db.String(36), primary_key=True)  # UUID
    title = db.Column(db.String(200), nullable=False)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    options = db.relationship('Option', backref='poll', lazy=True)


class Option(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(200), nullable=False)
    votes = db.Column(db.Integer, default=0)
    poll_id = db.Column(db.String(36), db.ForeignKey('poll.id'), nullable=False)


class Vote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    poll_id = db.Column(db.String(36), db.ForeignKey('poll.id'), nullable=False)
    option_id = db.Column(db.Integer, db.ForeignKey('option.id'), nullable=False)

    user = db.relationship('User', backref=db.backref('votes', lazy=True))
    poll = db.relationship('Poll', backref=db.backref('votes', lazy=True))
    option = db.relationship('Option', backref=db.backref('option_votes', lazy=True))  # schimbăm numele backref


with app.app_context():
    #db.drop_all()  # Șterge toate tabelele
    db.create_all()  # Crează noile tabele cu schema actualizată



@app.route('/')
def index():
    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if User.query.filter_by(username=username).first():
            return "Username already exists!"

        hashed_password = generate_password_hash(password)
        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['username'] = username

            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            return "Invalid credentials!"

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('index'))


@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))

    user = User.query.filter_by(username=session['username']).first()
    polls = Poll.query.filter_by(creator_id=user.id).all()
    return render_template('dashboard.html', polls=polls)


@app.route('/create_poll', methods=['GET', 'POST'])
def create_poll():
    if 'username' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form['title']
        options = request.form.getlist('options')

        user = User.query.filter_by(username=session['username']).first()
        poll_id = str(uuid.uuid4())
        new_poll = Poll(id=poll_id, title=title, creator=user)
        db.session.add(new_poll)

        for option_text in options:
            option = Option(text=option_text, poll=new_poll)
            db.session.add(option)

        db.session.commit()
        return redirect(url_for('dashboard'))

    return render_template('create_poll.html')


@app.route('/poll/<poll_id>', methods=['GET', 'POST'])
def poll(poll_id):
    poll = Poll.query.get(poll_id)
    if not poll:
        return "Poll not found!"

    if 'username' not in session:
        return redirect(url_for('login', next=url_for('poll', poll_id=poll_id)))

    is_creator = False
    user = User.query.filter_by(username=session['username']).first()
    if user and poll.creator_id == user.id:
        is_creator = True

    existing_vote = Vote.query.filter_by(user_id=user.id, poll_id=poll.id).first()
    has_voted = existing_vote is not None

    if request.method == 'POST':
        if not is_creator and not has_voted:
            selected_option_ids = request.form.getlist('options[]')  # Get list of selected options
            if selected_option_ids:
                # Loop through all selected options and process the vote
                for selected_option_id in selected_option_ids:
                    option = Option.query.get(selected_option_id)
                    if option:
                        option.votes += 1
                        db.session.commit()

                        new_vote = Vote(user_id=user.id, poll_id=poll.id, option_id=selected_option_id)  # Save each vote
                        db.session.add(new_vote)
                db.session.commit()

        return redirect(url_for('poll', poll_id=poll_id))

    return render_template('poll.html', poll=poll, is_creator=is_creator, has_voted=has_voted)

@app.route('/delete/<poll_id>', methods=['GET'])
def delete_poll(poll_id):
    # Check if the user is logged in
    if 'username' not in session:
        return redirect(url_for('login'))

    user = User.query.filter_by(username=session['username']).first()
    if not user:
        return redirect(url_for('login'))

    # Get the poll to delete
    poll = Poll.query.get(poll_id)
    if not poll:
        return "Poll not found!"

    # Ensure the logged-in user is the creator of the poll
    if poll.creator_id != user.id:
        return "You are not the creator of this poll!"

    # Delete related votes
    Vote.query.filter_by(poll_id=poll_id).delete()

    # Delete options associated with the poll
    Option.query.filter_by(poll_id=poll_id).delete()

    # Delete the poll itself
    db.session.delete(poll)
    db.session.commit()

    return redirect(url_for('dashboard'))


@app.route('/poll/<poll_id>/results')
def poll_results(poll_id):
    poll = Poll.query.get(poll_id)
    if not poll:
        return "Poll not found!"

    if 'username' not in session:
        return "Access denied!"

    user = User.query.filter_by(username=session['username']).first()
    if not user or poll.creator_id != user.id:
        return "Access denied!"

    # Get all votes for the poll
    votes = Vote.query.filter_by(poll_id=poll.id).all()

    # Group votes by username
    vote_details = {}
    for vote in votes:
        user = User.query.get(vote.user_id)
        option = Option.query.get(vote.option_id)

        if user.username not in vote_details:
            vote_details[user.username] = []

        vote_details[user.username].append(option.text)

    # Convert the vote_details dictionary into a list of dictionaries for easier rendering
    grouped_votes = [{'username': username, 'options': options} for username, options in vote_details.items()]

    return render_template('results.html', poll=poll, grouped_votes=grouped_votes)



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)