-- Création des tables pour la Bibliothèque
CREATE TABLE Authors (
    author_id INT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    birth_year INT
);

CREATE TABLE Books (
    book_id INT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    author_id INT,
    published_year INT,
    FOREIGN KEY (author_id) REFERENCES Authors(author_id)
);

-- Insertion de données factices
INSERT INTO Authors (author_id, name, birth_year) VALUES (1, 'J.K. Rowling', 1965);
INSERT INTO Authors (author_id, name, birth_year) VALUES (2, 'George Orwell', 1903);

INSERT INTO Books (book_id, title, author_id, published_year) VALUES (101, 'Harry Potter and the Philosopher''s Stone', 1, 1997);
INSERT INTO Books (book_id, title, author_id, published_year) VALUES (102, '1984', 2, 1949);