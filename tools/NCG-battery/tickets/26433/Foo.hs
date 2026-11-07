module Foo where
data Foo = Foo
  { a :: !Int
  , b :: !Int
  , c :: !Int
  , d :: !Int
  , e :: !Int
  , f :: !Int
  , g :: !Int
  , h :: !Int
  , i :: !Int
  , j :: !Int
  , k :: !Int
  , l :: !Int
  , m :: !Int
  , n :: !Int
  , o :: !Int
  , p :: !Int
  , q :: !Int
  }

foo :: Foo -> Foo
foo fo = fo { d = 17 }               
